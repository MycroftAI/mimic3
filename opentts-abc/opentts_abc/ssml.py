#!/usr/bin/env python3
import enum
import logging
import re
import typing
import xml.etree.ElementTree as etree
from dataclasses import dataclass

from opentts_abc import (
    BaseResult,
    Phonemes,
    SayAs,
    Settings,
    TextToSpeechSystem,
    Word,
)

LOG = logging.getLogger("opentts_abc.ssml")
NO_NAMESPACE_PATTERN = re.compile(r"^{[^}]+}")


@dataclass
class EndElement:
    """Wrapper for end of an XML element (used in TextProcessor)"""

    element: etree.Element


class ParsingState(int, enum.Enum):
    """Current state of SSML parsing"""

    DEFAULT = enum.auto()

    IN_SENTENCE = enum.auto()
    """Inside <s>"""

    IN_WORD = enum.auto()
    """Inside <w> or <token>"""

    IN_SUB = enum.auto()
    """Inside <sub>"""

    IN_PHONEME = enum.auto()
    """Inside <phoneme>"""

    IN_LEXICON = enum.auto()
    """Inside <lexicon>"""

    IN_LEXICON_GRAPHEME = enum.auto()
    """Inside <lexicon><grapheme>..."""

    IN_LEXICON_PHONEME = enum.auto()
    """Inside <lexicon><phoneme>..."""

    IN_METADATA = enum.auto()
    """Inside <metadata>"""

    IN_SAY_AS = enum.auto()
    """Inside <say-as>"""


# -----------------------------------------------------------------------------


class SSMLSpeaker:
    def __init__(self, tts: TextToSpeechSystem):
        self.state_stack: typing.List[ParsingState] = [ParsingState.DEFAULT]
        self.element_stack: typing.List[etree.Element] = []
        self.voice_stack: typing.List[str] = []
        self.lang_stack: typing.List[str] = []
        self.interpret_as: typing.Optional[str] = None
        self.say_as_format: typing.Optional[str] = None
        self.tts = tts

    def speak(
        self, ssml: typing.Union[str, etree.Element]
    ) -> typing.Iterable[BaseResult]:

        if isinstance(ssml, etree.Element):
            root_element = ssml
        else:
            root_element = etree.fromstring(ssml)

        # Process sub-elements and text chunks
        for elem_or_text in text_and_elements(root_element):
            if isinstance(elem_or_text, str):
                if self.state in {ParsingState.IN_METADATA}:
                    # Skip metadata text
                    continue

                # Text chunk
                text = typing.cast(str, elem_or_text)
                self.handle_text(text)
            elif isinstance(elem_or_text, EndElement):
                # End of an element (e.g., </w>)
                end_elem = typing.cast(EndElement, elem_or_text)
                end_tag = tag_no_namespace(end_elem.element.tag)

                if end_tag == "s":
                    yield from self.handle_end_sentence()
                elif end_tag in {"w", "token"}:
                    self.handle_end_word()
                elif end_tag in {"phoneme"}:
                    self.handle_end_phoneme()
                elif end_tag == "voice":
                    self.handle_end_voice()
                elif end_tag == "say-as":
                    self.handle_end_say_as()
                elif end_tag in {"sub"}:
                    # Handled in handle_text
                    pass
                elif end_tag in {"metadata", "meta"}:
                    self.handle_end_metadata()
                else:
                    LOG.debug("Ignoring end tag: %s", end_tag)
            else:
                if self.state in {ParsingState.IN_METADATA}:
                    # Skip metadata text
                    continue

                # Start of an element (e.g., <p>)
                elem, elem_metadata = elem_or_text
                elem = typing.cast(etree.Element, elem)

                # Optional metadata for the element
                elem_metadata = typing.cast(
                    typing.Optional[typing.Dict[str, typing.Any]], elem_metadata
                )

                elem_tag = tag_no_namespace(elem.tag)

                if elem_tag == "s":
                    self.handle_begin_sentence()
                elif elem_tag in {"w", "token"}:
                    self.handle_begin_word(elem)
                elif elem_tag == "sub":
                    self.handle_begin_sub(elem)
                elif elem_tag == "phoneme":
                    self.handle_begin_phoneme(elem)
                elif elem_tag == "break":
                    self.handle_break(elem)
                elif elem_tag == "mark":
                    self.handle_mark(elem)
                elif elem_tag == "voice":
                    self.handle_begin_voice(elem)
                elif elem_tag == "say-as":
                    self.handle_begin_say_as(elem)
                elif elem_tag in {"metadata", "meta"}:
                    self.handle_begin_metadata()
                else:
                    LOG.debug("Ignoring start tag: %s", elem_tag)

        assert self.state in {
            ParsingState.IN_SENTENCE,
            ParsingState.DEFAULT,
        }, self.state
        if self.state in {ParsingState.IN_SENTENCE}:
            yield from self.handle_end_sentence()

    # -------------------------------------------------------------------------

    def handle_text(self, text: str):
        assert self.state in {
            ParsingState.DEFAULT,
            ParsingState.IN_SENTENCE,
            ParsingState.IN_WORD,
            ParsingState.IN_SUB,
            ParsingState.IN_PHONEME,
            ParsingState.IN_SAY_AS,
        }, self.state

        if self.state == ParsingState.IN_PHONEME:
            # Phonemes were emitted in handle_begin_phoneme
            return

        if self.state == ParsingState.IN_SUB:
            # Substitute text
            assert self.element is not None
            text = attrib_no_namespace(self.element, "alias", "")
            LOG.debug("alias text: %s", text)

            # Terminate <sub> early
            self.handle_end_sub()

        if self.state == ParsingState.DEFAULT:
            self.handle_begin_sentence()

        LOG.debug("text: %s", text)

        if self.state == ParsingState.IN_WORD:
            self.handle_word(text, self.element)
        elif self.state == ParsingState.IN_SAY_AS:
            assert self.interpret_as is not None
            self.tts.speak_tokens(
                [
                    SayAs(
                        text=text,
                        interpret_as=self.interpret_as,
                        format=self.say_as_format,
                    )
                ]
            )
        else:
            self.tts.speak_text(text)

    def handle_begin_word(self, elem: etree.Element):
        LOG.debug("begin word")
        self.push_element(elem)
        self.push_state(ParsingState.IN_WORD)

    def handle_word(self, text: str, elem: typing.Optional[etree.Element] = None):
        assert self.state in {ParsingState.IN_WORD}, self.state

        role: typing.Optional[str] = None
        if elem is not None:
            role = attrib_no_namespace(elem, "role")

        self.tts.speak_tokens([Word(text, role=role)])

    def handle_end_word(self):
        LOG.debug("end word")
        assert self.state in {ParsingState.IN_WORD}, self.state
        self.pop_state()
        self.pop_element()

    def handle_begin_sub(self, elem: etree.Element):
        LOG.debug("begin sub")
        self.push_element(elem)
        self.push_state(ParsingState.IN_SUB)

    def handle_end_sub(self):
        LOG.debug("end sub")
        assert self.state in {ParsingState.IN_SUB}, self.state
        self.pop_state()
        self.pop_element()

    def handle_begin_phoneme(self, elem: etree.Element):
        LOG.debug("begin phoneme")

        if self.state == ParsingState.DEFAULT:
            self.handle_begin_sentence()

        phonemes = attrib_no_namespace(elem, "ph", "")
        alphabet = attrib_no_namespace(elem, "alphabet", "")

        LOG.debug("phonemes: %s", phonemes)

        self.tts.speak_tokens([Phonemes(text=phonemes, alphabet=alphabet)])

        self.push_element(elem)
        self.push_state(ParsingState.IN_PHONEME)

    def handle_end_phoneme(self):
        LOG.debug("end phoneme")
        assert self.state in {ParsingState.IN_PHONEME}, self.state
        self.pop_state()
        self.pop_element()

    def handle_begin_metadata(self):
        LOG.debug("begin metadata")
        self.push_state(ParsingState.IN_METADATA)

    def handle_end_metadata(self):
        LOG.debug("end metadata")
        assert self.state in {ParsingState.IN_METADATA}, self.state
        self.pop_state()

    def handle_begin_sentence(self):
        LOG.debug("begin sentence")
        assert self.state in {ParsingState.DEFAULT}, self.state
        self.push_state(ParsingState.IN_SENTENCE)
        self.tts.begin_utterance()

    def handle_end_sentence(self) -> typing.Iterable[BaseResult]:
        LOG.debug("end sentence")
        assert self.state in {ParsingState.IN_SENTENCE}, self.state
        self.pop_state()

        yield from self.tts.end_utterance()

    def handle_begin_voice(self, elem: etree.Element):
        LOG.debug("begin voice")
        voice_name = attrib_no_namespace(elem, "name")

        LOG.debug("voice: %s", voice_name)
        self.push_voice(voice_name)

        # Set new voice
        self.tts.voice = voice_name

    def handle_end_voice(self):
        LOG.debug("end voice")
        voice_name = self.pop_voice()

        # Restore voice
        self.tts.voice = voice_name

    def handle_break(self, elem: etree.Element):
        time_str = attrib_no_namespace(elem, "time", "").strip()
        time_ms: int = 0

        if time_str.endswith("ms"):
            time_ms = int(time_str[:-2])
        elif time_str.endswith("s"):
            time_ms = int(float(time_str[:-1]) * 1000)

        if time_ms > 0:
            LOG.debug("Break: %s ms", time_ms)
            self.tts.add_break(time_ms)

    def handle_mark(self, elem: etree.Element):
        name = attrib_no_namespace(elem, "name", "")

        LOG.debug("Mark: %s", name)
        self.tts.set_mark(name)

    def handle_begin_say_as(self, elem: etree.Element):
        LOG.debug("begin say-as")
        self.interpret_as = attrib_no_namespace(elem, "interpret-as", "")
        self.say_as_format = attrib_no_namespace(elem, "format", "")

        LOG.debug("Say as %s, format=%s", self.interpret_as, self.say_as_format)
        self.push_state(ParsingState.IN_SAY_AS)

    def handle_end_say_as(self):
        LOG.debug("end say-as")
        assert self.state in {ParsingState.IN_SAY_AS}
        self.interpret_as = None
        self.say_as_format = None
        self.pop_state()

    # -------------------------------------------------------------------------

    @property
    def state(self) -> ParsingState:
        if self.state_stack:
            return self.state_stack[-1]

        return ParsingState.DEFAULT

    def push_state(self, new_state: ParsingState):
        self.state_stack.append(new_state)

    def pop_state(self) -> ParsingState:
        if self.state_stack:
            return self.state_stack.pop()

        return ParsingState.DEFAULT

    @property
    def element(self) -> typing.Optional[etree.Element]:
        if self.element_stack:
            return self.element_stack[-1]

        return None

    def push_element(self, new_element: etree.Element):
        self.element_stack.append(new_element)

    def pop_element(self) -> typing.Optional[etree.Element]:
        if self.element_stack:
            return self.element_stack.pop()

        return None

    @property
    def lang(self) -> typing.Optional[str]:
        if self.lang_stack:
            return self.lang_stack[-1]

        return self.tts.language

    def push_lang(self, new_lang: str):
        self.lang_stack.append(new_lang)

    def pop_lang(self) -> typing.Optional[str]:
        if self.lang_stack:
            return self.lang_stack.pop()

        return self.tts.language

    @property
    def voice(self) -> typing.Optional[str]:
        if self.voice_stack:
            return self.voice_stack[-1]

        return self.tts.voice

    def push_voice(self, new_voice: str):
        self.voice_stack.append(new_voice)

    def pop_voice(self) -> typing.Optional[str]:
        if self.voice_stack:
            return self.voice_stack.pop()

        return self.tts.voice


# -----------------------------------------------------------------------------


def tag_no_namespace(tag: str) -> str:
    """Remove namespace from XML tag"""
    return NO_NAMESPACE_PATTERN.sub("", tag)


def attrib_no_namespace(
    element: etree.Element, name: str, default: typing.Any = None
) -> typing.Any:
    """Search for an attribute by key without namespaces"""
    for key, value in element.attrib.items():
        key_no_ns = NO_NAMESPACE_PATTERN.sub("", key)
        if key_no_ns == name:
            return value

    return default


def text_and_elements(element, is_last=False):
    """Yields element, text, sub-elements, end element, and tail"""
    element_metadata = None

    if is_last:
        # True if this is the last child element of a parent.
        # Used to preserve whitespace.
        element_metadata = {"is_last": True}

    yield element, element_metadata

    # Text before any tags (or end tag)
    text = element.text if element.text is not None else ""
    if text.strip():
        yield text

    children = list(element)
    last_child_idx = len(children) - 1

    for child_idx, child in enumerate(children):
        # Sub-elements
        is_last = child_idx == last_child_idx
        yield from text_and_elements(child, is_last=is_last)

    # End of current element
    yield EndElement(element)

    # Text after the current tag
    tail = element.tail if element.tail is not None else ""
    if tail.strip():
        yield tail
