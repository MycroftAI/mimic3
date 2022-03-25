# Open Text to Speech (TTS) Abstract Base Classes (ABC)

Base classes for open text to speech systems.


## SSML

A subset of [SSML](https://www.w3.org/TR/speech-synthesis11/) is supported in `SSMLSpeaker`:

* `<speak>` - wrap around SSML text
    * `lang` - set language for document
* `<s>` - sentence (disables automatic sentence breaking)
    * `lang` - set language for sentence
* `<w>` / `<token>` - word (disables automatic tokenization)
* `<voice name="...">` - set voice of inner text
    * `voice` - name of voice
* `<say-as interpret-as="">` - force interpretation of inner text
    * `interpret-as` - way to interpret text (implementation dependent)
    * `format` - way to format text (implementation dependent)
* `<break time="">` - Pause for given amount of time
    * time - seconds ("123s") or milliseconds ("123ms")
* `<mark name="">` - User-defined mark (written to `--mark-file` or part of `TextToSpeechResult`)
    * name - name of mark
* `<sub alias="">` - substitute `alias` for inner text
* `<phoneme ph="..." alphabet="ipa">` - supply phonemes for inner text
    * `ph` - phonemes for each word of inner text
    * `alphabet` - name of phoneme alphabet (usually "ipa")
