# Mimic 3

A fast and local neural text to speech system for [Mycroft](https://mycroft.ai/) and the [Mark II](https://mycroft.ai/product/mark-ii/).

[Available voices](https://github.com/MycroftAI/mimic3-voices)


## Command-Line Tools


### mimic3


### mimic3-download


## SSML

A subset of [SSML](https://www.w3.org/TR/speech-synthesis11/) is supported:

* `<speak>` - wrap around SSML text
    * `lang` - set language for document
* `<s>` - sentence (disables automatic sentence breaking)
    * `lang` - set language for sentence
* `<w>` / `<token>` - word (disables automatic tokenization)
* `<voice name="...">` - set voice of inner text
    * `voice` - name or language of voice
        * Name format is `tts:voice` (e.g., "glow-speak:en-us_mary_ann") or `tts:voice#speaker_id` (e.g., "coqui-tts:en_vctk#p228")
        * If one of the supported languages, a preferred voice is used (override with `--preferred-voice <lang> <voice>`)
* `<say-as interpret-as="">` - force interpretation of inner text
    * `interpret-as` one of "spell-out", "date", "number", "time", or "currency"
    * `format` - way to format text depending on `interpret-as`
        * number - one of "cardinal", "ordinal", "digits", "year"
        * date - string with "d" (cardinal day), "o" (ordinal day), "m" (month), or "y" (year)
* `<break time="">` - Pause for given amount of time
    * time - seconds ("123s") or milliseconds ("123ms")
* `<sub alias="">` - substitute `alias` for inner text


## Architecture

Mimic 3 uses the [VITS](https://arxiv.org/abs/2106.06103), a "Conditional Variational Autoencoder with Adversarial Learning for End-to-End Text-to-Speech". VITS is a combination of the [GlowTTS duration predictor](https://arxiv.org/abs/2005.11129) and the [HiFi-GAN vocoder](https://arxiv.org/abs/2010.05646).

Our implementation is heavily based on [Jaehyeon Kim's PyTorch model](https://github.com/jaywalnut310/vits), with the addition of [Onnx runtime](https://onnxruntime.ai/) export for speed. 


### gruut Phoneme-based Voices

Voices that use [gruut](https://github.com/rhasspy/gruut/) for phonemization.


### eSpeak Phoneme-based Voices

Voices that use [eSpeak-ng](https://github.com/espeak-ng/espeak-ng) for phonemization (via [espeak-phonemizer](https://github.com/rhasspy/espeak-phonemizer)).


### Character-based Voices

Voices whose "phonemes" are characters from an alphabet, typically with some punctuation.


## License

See [license file](LICENSE)
