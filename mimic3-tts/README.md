# Mimic 3

A fast and local neural text to speech system for [Mycroft](https://mycroft.ai/) and the [Mark II](https://mycroft.ai/product/mark-ii/).


## Architecture

Mimic 3 uses the [VITS](https://arxiv.org/abs/2106.06103), a "Conditional Variational Autoencoder with Adversarial Learning for End-to-End Text-to-Speech". VITS is a combination of the [GlowTTS duration predictor](https://arxiv.org/abs/2005.11129) and the [HiFi-GAN vocoder](https://arxiv.org/abs/2010.05646).

Our implementation is heavily based on [Jaehyeon Kim's PyTorch model](https://github.com/jaywalnut310/vits), with the addition of [Onnx runtime](https://onnxruntime.ai/) export for speed. 


### gruut Phoneme-based Voices

Voices that use [gruut](https://github.com/rhasspy/gruut/) for phonemization.


### eSpeak Phoneme-based Voices

Voices that use [eSpeak-ng](https://github.com/espeak-ng/espeak-ng) for phonemization (via [espeak-phonemizer](https://github.com/rhasspy/espeak-phonemizer)).


### Character-based Voices

Voices whose "phonemes" are characters from an alphabet, typically with some punctuation.
