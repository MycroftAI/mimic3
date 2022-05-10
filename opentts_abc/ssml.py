# Copyright 2022 Mycroft AI Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""Support for Speech Synthesis Markup Language (SSML)"""
import dataclasses
import enum
import logging
import re
import typing
import xml.etree.ElementTree as etree
from dataclasses import dataclass, field

from opentts_abc import BaseResult, Phonemes, SayAs, TextToSpeechSystem, Word

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

    IN_METADATA = enum.auto()
    """Inside <metadata>"""

    IN_SAY_AS = enum.auto()
    """Inside <say-as>"""

    IN_PROSODY = enum.auto()
    """Inside <prosody>"""


_DEFAULT_VOLUME: float = 100.0
_DEFAULT_RATE: float = 1.0


@dataclass
class ProsodyState:
    """Current prosody settings"""

    volume: float = _DEFAULT_VOLUME
    """Currrent volume setting in [0, 100]"""

    rate: float = _DEFAULT_RATE
    """Current rate setting (< 1 is slower, > 1 is faster)"""


# -----------------------------------------------------------------------------

_DEFAULT_VOLUME_MAP = {
    "default": _DEFAULT_VOLUME,
    "x-loud": _DEFAULT_VOLUME,
    "loud": _DEFAULT_VOLUME * 0.8,
    "medium": _DEFAULT_VOLUME * 0.5,
    "soft": _DEFAULT_VOLUME * 0.3,
    "x-soft": _DEFAULT_VOLUME * 0.1,
    "silent": 0.0,
}

_DEFAULT_RATE_MAP = {
    "default": _DEFAULT_RATE,
    "x-fast": _DEFAULT_RATE * 3,
    "fast": _DEFAULT_RATE * 2,
    "medium": _DEFAULT_RATE,
    "slow": _DEFAULT_RATE * 0.5,
    "x-slow": _DEFAULT_RATE * 0.25,
}


@dataclass
class SSMLSettings:
    """Settings for SSML named constants"""

    volume_map: typing.Mapping[str, float] = field(
        default_factory=lambda: _DEFAULT_VOLUME_MAP
    )
    """Volume named constant to volume level"""

    rate_map: typing.Mapping[str, float] = field(
        default_factory=lambda: _DEFAULT_RATE_MAP
    )
    """Rate named constant to speaking rate"""


# -----------------------------------------------------------------------------


class SSMLSpeaker:
    """Wrapper for TextToSpeechSystem that parses/implements SSML.

    See: https://www.w3.org/TR/speech-synthesis11/
    """

    def __init__(
        self, tts: TextToSpeechSystem, settings: typing.Optional[SSMLSettings] = None
    ):
        self.tts = tts
        self.settings = settings or SSMLSettings()

        self._state_stack: typing.List[ParsingState] = [ParsingState.DEFAULT]
        self._element_stack: typing.List[etree.Element] = []
        self._voice_stack: typing.List[str] = []
        self._lang_stack: typing.List[str] = []
        self._interpret_as: typing.Optional[str] = None
        self._say_as_format: typing.Optional[str] = None
        self._prosody_stack: typing.List[ProsodyState] = []

        self._default_voice = self.tts.voice
        self._default_lang = self.tts.language
        self._default_prosody = ProsodyState()

    def speak(
        self, ssml: typing.Union[str, etree.Element]
    ) -> typing.Iterable[BaseResult]:
        """Parses and realizes a set of SSML utterances using the underlying TextToSpeechSystem"""

        if isinstance(ssml, etree.Element):
            root_element = ssml
        else:
            try:
                root_element = etree.fromstring(ssml)
            except etree.ParseError:
                # Try again wrapped in <speak>
                root_element = etree.fromstring(f"<speak>{ssml}</speak>")

        # Process sub-elements and text chunks
        for elem_or_text in text_and_elements(root_element):
            if isinstance(elem_or_text, str):
                if self._state in {ParsingState.IN_METADATA}:
                    # Skip metadata text
                    continue

                # Text chunk
                text = typing.cast(str, elem_or_text)
                self._handle_text(text)
            elif isinstance(elem_or_text, EndElement):
                # End of an element (e.g., </w>)
                end_elem = typing.cast(EndElement, elem_or_text)
                end_tag = tag_no_namespace(end_elem.element.tag)

                if end_tag == "s":
                    yield from self._handle_end_sentence()
                elif end_tag in {"w", "token"}:
                    self._handle_end_word()
                elif end_tag in {"phoneme"}:
                    self._handle_end_phoneme()
                elif end_tag == "voice":
                    self._handle_end_voice()
                elif end_tag == "say-as":
                    self._handle_end_say_as()
                elif end_tag == "lang":
                    self._handle_end_lang()
                elif end_tag == "prosody":
                    self._handle_end_prosody()
                elif end_tag in {"sub"}:
                    # Handled in handle_text
                    pass
                elif end_tag in {"metadata", "meta"}:
                    self._handle_end_metadata()
                elif end_tag == "speak":
                    yield from self._handle_end_speak()
                else:
                    LOG.debug("Ignoring end tag: %s", end_tag)
            else:
                if self._state in {ParsingState.IN_METADATA}:
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
                    self._handle_begin_sentence()
                elif elem_tag in {"w", "token"}:
                    self._handle_begin_word(elem)
                elif elem_tag == "sub":
                    self._handle_begin_sub(elem)
                elif elem_tag == "phoneme":
                    self._handle_begin_phoneme(elem)
                elif elem_tag == "break":
                    self._handle_break(elem)
                elif elem_tag == "mark":
                    self._handle_mark(elem)
                elif elem_tag == "voice":
                    self._handle_begin_voice(elem)
                elif elem_tag == "say-as":
                    self._handle_begin_say_as(elem)
                elif elem_tag == "lang":
                    self._handle_begin_lang(elem)
                elif elem_tag == "prosody":
                    self._handle_begin_prosody(elem)
                elif elem_tag in {"metadata", "meta"}:
                    self._handle_begin_metadata()
                else:
                    LOG.debug("Ignoring start tag: %s", elem_tag)

        assert self._state in {
            ParsingState.IN_SENTENCE,
            ParsingState.DEFAULT,
        }, self._state

        if self._state in {ParsingState.IN_SENTENCE}:
            yield from self._handle_end_sentence()

    # -------------------------------------------------------------------------

    def _handle_text(self, text: str):
        """Handle sentence/word text"""
        assert self._state in {
            ParsingState.DEFAULT,
            ParsingState.IN_SENTENCE,
            ParsingState.IN_WORD,
            ParsingState.IN_SUB,
            ParsingState.IN_PHONEME,
            ParsingState.IN_SAY_AS,
        }, self._state

        if self._state == ParsingState.IN_PHONEME:
            # Phonemes were emitted in handle_begin_phoneme
            return

        if self._state == ParsingState.IN_SUB:
            # Substitute text
            assert self._element is not None
            text = attrib_no_namespace(self._element, "alias", "")
            LOG.debug("alias text: %s", text)

            # Terminate <sub> early
            self._handle_end_sub()

        if self._state == ParsingState.DEFAULT:
            self._handle_begin_sentence()

        LOG.debug("text: %s", text)

        if self._state == ParsingState.IN_WORD:
            self._handle_word(text, self._element)
        elif self._state == ParsingState.IN_SAY_AS:
            assert self._interpret_as is not None
            self.tts.speak_tokens(
                [
                    SayAs(
                        text=text,
                        interpret_as=self._interpret_as,
                        format=self._say_as_format,
                    )
                ]
            )
        else:
            self.tts.speak_text(text)

    def _handle_begin_word(self, elem: etree.Element):
        """Handle <w> or <t>"""
        LOG.debug("begin word")
        self._push_element(elem)
        self._push_state(ParsingState.IN_WORD)

    def _handle_word(self, text: str, elem: typing.Optional[etree.Element] = None):
        """Handle text from word"""
        assert self._state in {ParsingState.IN_WORD}, self._state

        role: typing.Optional[str] = None
        if elem is not None:
            role = attrib_no_namespace(elem, "role")

        self.tts.speak_tokens([Word(text, role=role)])

    def _handle_end_word(self):
        """Handle </w> or </t>"""
        LOG.debug("end word")
        assert self._state in {ParsingState.IN_WORD}, self._state
        self._pop_state()
        self._pop_element()

    def _handle_begin_sub(self, elem: etree.Element):
        """Handle <sub>"""
        LOG.debug("begin sub")
        self._push_element(elem)
        self._push_state(ParsingState.IN_SUB)

    def _handle_end_sub(self):
        """Handle </sub>"""
        LOG.debug("end sub")
        assert self._state in {ParsingState.IN_SUB}, self._state
        self._pop_state()
        self._pop_element()

    def _handle_begin_phoneme(self, elem: etree.Element):
        """Handle <phoneme>"""
        LOG.debug("begin phoneme")

        if self._state == ParsingState.DEFAULT:
            self._handle_begin_sentence()

        phonemes = attrib_no_namespace(elem, "ph", "")
        alphabet = attrib_no_namespace(elem, "alphabet", "")

        LOG.debug("phonemes: %s", phonemes)

        self.tts.speak_tokens([Phonemes(text=phonemes, alphabet=alphabet)])

        self._push_element(elem)
        self._push_state(ParsingState.IN_PHONEME)

    def _handle_end_phoneme(self):
        """Handle </phoneme>"""
        LOG.debug("end phoneme")
        assert self._state in {ParsingState.IN_PHONEME}, self._state
        self._pop_state()
        self._pop_element()

    def _handle_begin_metadata(self):
        """Handle <metadata>"""
        LOG.debug("begin metadata")
        self._push_state(ParsingState.IN_METADATA)

    def _handle_end_metadata(self):
        """Handle </metadata>"""
        LOG.debug("end metadata")
        assert self._state in {ParsingState.IN_METADATA}, self._state
        self._pop_state()

    def _handle_begin_sentence(self):
        """Handle <s>"""
        LOG.debug("begin sentence")
        assert self._state in {ParsingState.DEFAULT}, self._state
        self._push_state(ParsingState.IN_SENTENCE)
        self.tts.begin_utterance()

    def _handle_end_sentence(self) -> typing.Iterable[BaseResult]:
        """Handle </s>"""
        LOG.debug("end sentence")
        assert self._state in {ParsingState.IN_SENTENCE}, self._state
        self._pop_state()

        yield from self.tts.end_utterance()

    def _handle_end_speak(self) -> typing.Iterable[BaseResult]:
        """Handle </speak>"""
        LOG.debug("end speak")
        if self._state == ParsingState.IN_SENTENCE:
            yield from self._handle_end_sentence()

        assert self._state in {ParsingState.DEFAULT}, self._state

        yield from self.tts.end_utterance()

    def _handle_begin_voice(self, elem: etree.Element):
        """Handle <voice>"""
        LOG.debug("begin voice")
        voice_name = attrib_no_namespace(elem, "name")

        LOG.debug("voice: %s", voice_name)
        self._push_voice(voice_name)

        # Set new voice
        self.tts.voice = voice_name

    def _handle_end_voice(self):
        """Handle </voice>"""
        LOG.debug("end voice")
        self._pop_voice()

        # Restore voice
        self.tts.voice = self._voice
        LOG.debug("voice: %s", self._voice)

    def _handle_break(self, elem: etree.Element):
        """Handle <break>"""
        time_str = attrib_no_namespace(elem, "time", "").strip()
        time_ms: int = 0

        if time_str.endswith("ms"):
            time_ms = int(time_str[:-2])
        elif time_str.endswith("s"):
            time_ms = int(float(time_str[:-1]) * 1000)

        if time_ms > 0:
            LOG.debug("Break: %s ms", time_ms)
            self.tts.add_break(time_ms)

    def _handle_mark(self, elem: etree.Element):
        """Handle <mark>"""
        name = attrib_no_namespace(elem, "name", "")

        LOG.debug("Mark: %s", name)
        self.tts.set_mark(name)

    def _handle_begin_say_as(self, elem: etree.Element):
        """Handle <say-as>"""
        LOG.debug("begin say-as")
        self._interpret_as = attrib_no_namespace(elem, "interpret-as", "")
        self._say_as_format = attrib_no_namespace(elem, "format", "")

        LOG.debug("Say as %s, format=%s", self._interpret_as, self._say_as_format)
        self._push_state(ParsingState.IN_SAY_AS)

    def _handle_end_say_as(self):
        """Handle </say-as>"""
        LOG.debug("end say-as")
        assert self._state in {ParsingState.IN_SAY_AS}
        self._interpret_as = None
        self._say_as_format = None
        self._pop_state()

    def _handle_begin_lang(self, elem: etree.Element):
        """Handle <lang>"""
        LOG.debug("begin lang")
        lang = attrib_no_namespace(elem, "lang")

        LOG.debug("language: %s", lang)
        self._push_lang(lang)

    def _handle_end_lang(self):
        """Handle </lang>"""
        LOG.debug("end lang")
        self._pop_lang()

        LOG.debug("language: %s", self._lang)

    def _handle_begin_prosody(self, elem: etree.Element):
        """Handle <prosody>"""
        LOG.debug("begin prosody")

        # Start from current settings
        new_prosody = ProsodyState(**dataclasses.asdict(self._prosody))

        volume_str = attrib_no_namespace(elem, "volume")
        if volume_str is not None:
            new_prosody.volume = self._parse_volume(
                volume_str, current_volume=self._prosody.volume
            )

        rate_str = attrib_no_namespace(elem, "rate")
        if rate_str is not None:
            new_prosody.rate = self._parse_rate(rate_str)

        LOG.debug("prosody: %s", new_prosody)
        self._push_prosody(new_prosody)

        self.tts.volume = new_prosody.volume
        self.tts.rate = new_prosody.rate

    def _handle_end_prosody(self):
        """Handle </prosody>"""
        LOG.debug("end prosody")
        self._pop_prosody()

        LOG.debug("prosody: %s", self._prosody)

        self.tts.volume = self._prosody.volume
        self.tts.rate = self._prosody.rate

    # -------------------------------------------------------------------------

    @property
    def _state(self) -> ParsingState:
        """Get state at the top of the stack"""
        if self._state_stack:
            return self._state_stack[-1]

        return ParsingState.DEFAULT

    def _push_state(self, new_state: ParsingState):
        """Push new state on to the stack"""
        self._state_stack.append(new_state)

    def _pop_state(self) -> ParsingState:
        """Pop state off the stack"""
        if self._state_stack:
            return self._state_stack.pop()

        return ParsingState.DEFAULT

    @property
    def _element(self) -> typing.Optional[etree.Element]:
        """Get XML element at the top of the stack"""
        if self._element_stack:
            return self._element_stack[-1]

        return None

    def _push_element(self, new_element: etree.Element):
        """Push new XML element on to the stack"""
        self._element_stack.append(new_element)

    def _pop_element(self) -> typing.Optional[etree.Element]:
        """Pop XML element off the stack"""
        if self._element_stack:
            return self._element_stack.pop()

        return None

    @property
    def _lang(self) -> typing.Optional[str]:
        """Get language at the top of the stack"""
        if self._lang_stack:
            return self._lang_stack[-1]

        return self._default_lang

    def _push_lang(self, new_lang: str):
        """Push new language on to the stack"""
        self._lang_stack.append(new_lang)

    def _pop_lang(self) -> typing.Optional[str]:
        """Pop language off the stop of the stack"""
        if self._lang_stack:
            return self._lang_stack.pop()

        return self._default_lang

    @property
    def _voice(self) -> typing.Optional[str]:
        """Get voice at the top of the stack"""
        if self._voice_stack:
            return self._voice_stack[-1]

        return self._default_voice

    def _push_voice(self, new_voice: str):
        """Push new voice on to the stack"""
        self._voice_stack.append(new_voice)

    def _pop_voice(self) -> typing.Optional[str]:
        """Pop voice off the top of the stack"""
        if self._voice_stack:
            return self._voice_stack.pop()

        return self._default_voice

    @property
    def _prosody(self) -> ProsodyState:
        """Get prosody settings at the top of the stack"""
        if self._prosody_stack:
            return self._prosody_stack[-1]

        return self._default_prosody

    def _push_prosody(self, new_prosody: ProsodyState):
        """Push new prosody settings on to the stack"""
        self._prosody_stack.append(new_prosody)

    def _pop_prosody(self) -> ProsodyState:
        """Pop prosody settings off the stop of the stack"""
        if self._prosody_stack:
            return self._prosody_stack.pop()

        return self._default_prosody

    def _parse_volume(
        self, volume_str: str, current_volume: float = _DEFAULT_VOLUME
    ) -> float:
        """Parse SSML volume from <prosody> into [0, 100] value"""
        volume = current_volume
        volume_str = volume_str.strip().lower()

        # Look up by name
        maybe_volume = self.settings.volume_map.get(volume_str)
        if maybe_volume is not None:
            volume = maybe_volume
        elif volume_str:
            is_positive_offset = False
            is_negative_offset = False
            is_percent = False

            if volume_str[0] in {"+", "-"}:
                if volume_str[0] == "+":
                    is_positive_offset = True
                else:
                    is_negative_offset = True

                volume_str = volume_str[1:]

            if volume_str[-1] == "%":
                is_percent = True
                volume_str = volume_str[:-1]

            volume_value = float(volume_str)
            if is_percent:
                if is_positive_offset:
                    volume += volume * (volume_value / 100.0)
                elif is_negative_offset:
                    volume -= volume * (volume_value / 100.0)
                else:
                    # Already on a [0, 100] scale
                    volume = volume_value
            elif is_positive_offset:
                volume += volume_value
            elif is_negative_offset:
                volume -= volume_value
            else:
                # Absolute value
                volume = volume_value

        return max(0, min(_DEFAULT_VOLUME, volume))

    def _parse_rate(self, rate_str: str) -> float:
        """Parse SSML rate from <prosody> into float"""
        rate = _DEFAULT_RATE
        rate_str = rate_str.strip().lower()

        maybe_rate = self.settings.rate_map.get(rate_str)
        if maybe_rate is not None:
            rate = maybe_rate
        elif rate_str:
            is_percent = False

            if rate_str[-1] == "%":
                is_percent = True
                rate_str = rate_str[:-1]

            rate_value = float(rate_str)

            if is_percent:
                # 50% = 0.5
                rate = rate_value / 100.0
            else:
                # Absolute value
                rate = rate_value

        return rate


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
