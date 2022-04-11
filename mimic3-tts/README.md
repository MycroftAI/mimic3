# Mimic 3

A fast and local neural text to speech system for [Mycroft](https://mycroft.ai/) and the [Mark II](https://mycroft.ai/product/mark-ii/).

* [Available voices](https://github.com/MycroftAI/mimic3-voices)
* [Mimic 3 Architecture](#architecture)


## Command-Line Tools


### mimic3


#### Basic Synthesis

```sh
mimic3 --voice <voice> "<text>" > output.wav
```

where `<voice>` is a [voice key](https://github.com/MycroftAI/mimic3/#voice-keys) like `en_UK/apope_low`.
`<TEXT>` may contain multiple sentences, which will be combined in the final output WAV file. These can also be [split into separate WAV files](#multiple-wav-output).


#### SSML Synthesis

```sh
mimic3 --ssml --voice <voice> "<ssml>" > output.wav
```

where `<ssml>` is valid [SSML](https://www.w3.org/TR/speech-synthesis11/). Not all SSML features are supported, see [the documentation](#ssml) for details.

If your SSML contains `<mark>` tags, add `--mark-file <file>` to the command-line and use `--interactive` mode. As the marks are encountered, their names will be written on separate lines to the file:

```sh
mimic3 --ssml --interactive --mark-file - '<speak>Test 1. <mark name="here" /> Test 2.</speak>'
```


#### Long Texts

If your text is very long, and you would like to listen to it as its being synthesized, use `--interactive` mode:

```sh
mimic3 --interactive < long.txt
```

Each input line will be synthesized and played (see `--play-program`). By default, 5 sentences will be kept in an output queue, only blocking synthesis when the queue is full. You can adjust this value with `--result-queue-size`.

If your long text is fixed-width with blank lines separating paragraphs like those from [Project Gutenberg](https://www.gutenberg.org/), use the `--process-on-blank-line` option so that sentences will not be broken at line boundaries. For example, you can listen to "Alice in Wonderland" like this:

```sh
curl --output - 'https://www.gutenberg.org/files/11/11-0.txt' | \
    mimic3 --interactive --process-on-blank-line
```


#### Multiple WAV Output

With `--output-dir` set to a directory, Mimic 3 will output a separate WAV file for each sentence:

```sh
mimic3 'Test 1. Test 2.' --output-dir /path/to/wavs
```

By default, each WAV file will be named using the (slightly modified) text of the sentence. You can have WAV files named using a timestamp instead with `--output-naming time`. For full control of the output naming, the `--csv` command-line flag indicates that each sentence is of the form `id|text` where `id` will be the name of the WAV file.

```sh
cat << EOF |
s01|The birch canoe slid on the smooth planks.
s02|Glue the sheet to the dark blue background.
s03|It's easy to tell the depth of a well.
s04|These days a chicken leg is a rare dish.
s05|Rice is often served in round bowls.
s06|The juice of lemons makes fine punch.
s07|The box was thrown beside the parked truck.
s08|The hogs were fed chopped corn and garbage.
s09|Four hours of steady work faced us.
s10|Large size in stockings is hard to sell.
EOF
  mimic3 --csv --output-dir /path/to/wavs
```

You can adjust the delimiter with `--csv-delimiter <delimiter>`.

Additionally, you can use the `--csv-voice` option to specify a different voice or speaker for each line:

```sh
cat << EOF |
s01|#awb|The birch canoe slid on the smooth planks.
s02|#rms|Glue the sheet to the dark blue background.
s03|#slt|It's easy to tell the depth of a well.
s04|#ksp|These days a chicken leg is a rare dish.
s05|#clb|Rice is often served in round bowls.
s06|#aew|The juice of lemons makes fine punch.
s07|#bdl|The box was thrown beside the parked truck.
s08|#lnh|The hogs were fed chopped corn and garbage.
s09|#jmk|Four hours of steady work faced us.
s10|en_UK/apope_low|Large size in stockings is hard to sell.
EOF
  mimic3 --voice 'en_US/cmu-arctic_low' --csv-voice --output-dir /path/to/wavs
```

The second contain can contain a `#<speaker>` or an entirely different voice!


#### Interactive Mode

With `--interactive`, Mimic 3 will switch into interactive mode. After entering a sentence, it will be played with `--play-program`.

```sh
mimic3 --interactive
Reading text from stdin...
Hello world!<ENTER>
```

Use `CTRL+D` or `CTRL+C` to exit.


#### Noise and Length Settings

Synthesis has the following additional parameters:

* `--noise-scale` and `--noise-w`
    * Determine the speaker volatility during synthesis
    * 0-1, default is 0.667 and 0.8 respectively
* `--length-scale` - makes the voice speaker slower (> 1) or faster (< 1)

Individual voices have default settings for these parameters in their `config.json` files (under `inference`).


#### List Voices

```sh
mimic3 --voices
```


#### CUDA Acceleration

If you have a GPU with support for CUDA, you can accelerate synthesis with the `--cuda` flag. This requires you to install the [onnxruntime-gpu](https://pypi.org/project/onnxruntime-gpu/) Python package.

Using [nvidia-docker](https://github.com/NVIDIA/nvidia-docker) is highly recommended. See the `Dockerfile.gpu` file in the parent repository for an example of how to build a compatible container.



### mimic3-download

Mimic 3 automatically downloads voices when they're first used, but you can manually download them too with `mimic3-download`.

For example:

``` sh
mimic3-download 'en_US/*'
```

will download all U.S. English voices to `${HOME}/.local/share/mimic3` (technically `${XDG_DATA_HOME}/mimic3`).

See `mimic3-download --help` for more options.


## SSML

A subset of [SSML](https://www.w3.org/TR/speech-synthesis11/) (Speech Synthesis Markup Language) is supported:

* `<speak>` - wrap around SSML text
    * `lang` - set language for document
* `<s>` - sentence (disables automatic sentence breaking)
    * `lang` - set language for sentence
* `<w>` / `<token>` - word (disables automatic tokenization)
* `<voice name="...">` - set voice of inner text
    * `voice` - name or language of voice
        * Name format is `tts:voice` (e.g., "glow-speak:en-us_mary_ann") or `tts:voice#speaker_id` (e.g., "coqui-tts:en_vctk#p228")
        * If one of the supported languages, a preferred voice is used (override with `--preferred-voice <lang> <voice>`)
* `<prosody attribute="value">` - change speaking attributes
    * Supported `attribute` names:
        * `volume` - speaking volume
            * number in [0, 100] - 0 is silent, 100 is loudest (default)
            * +X, -X, +X%, -X% - absolute/percent offset from current volume
            * one of "default", "silent", "x-loud", "loud", "medium", "soft", "x-soft"
        * `rate` - speaking rate
            * number - 1 is default rate, < 1 is slower, > 1 is faster
            * X% - 100% is default rate, 50% is half speed, 200% is twice as fast
            * one of "default", "x-fast", "fast", "medium", "slow", "x-slow"
* `<say-as interpret-as="">` - force interpretation of inner text
    * `interpret-as` one of "spell-out", "date", "number", "time", or "currency"
    * `format` - way to format text depending on `interpret-as`
        * number - one of "cardinal", "ordinal", "digits", "year"
        * date - string with "d" (cardinal day), "o" (ordinal day), "m" (month), or "y" (year)
* `<break time="">` - Pause for given amount of time
    * time - seconds ("123s") or milliseconds ("123ms")
* `<sub alias="">` - substitute `alias` for inner text
* `<phoneme ph="">` - supply phonemes for inner text
    * See `phonemes.txt` in voice directory for available phonemes
    * Phonemes may need to be separated by whitespace

SSML `<say-as>` support varies between voice types:

* [gruut](https://github.com/rhasspy/gruut/#ssml)
* [eSpeak-ng](http://espeak.sourceforge.net/ssml.html)
* Character-based voices do not currently support `<say-as>`


## Speech Dispatcher

Mimic 3 can be used with the [Orca screen reader](https://help.gnome.org/users/orca/stable/) for Linux via [speech-dispatcher](https://github.com/brailcom/speechd).

After [installing Mimic 3](https://github.com/MycroftAI/mimic3/#installation), make sure you also have speech-dispatcher installed:

``` sh
sudo apt-get install speech-dispatcher
```

Create the file `/etc/speech-dispatcher/modules/mimic3-generic.conf` with the contents:

``` text
GenericExecuteSynth "printf %s \'$DATA\' | /path/to/mimic3 --remote --voice \'$VOICE\' --stdout | $PLAY_COMMAND"
AddVoice "en-us" "MALE1" "en_UK/apope_low"
```

You will need `sudo` access to do this. Make sure to change `/path/to/mimic3` to wherever you installed Mimic 3. Note that the `--remote` option is used to connect to a local Mimic 3 web server (use `--remote <URL>` if your server is somewhere besides `localhost`).

To change the voice later, you only need to replace `en_UK/apope_low`.

Next, edit the existing file `/etc/speech-dispatcher/speechd.conf` and ensure the following settings are present:

``` text
DefaultVoiceType  "MALE1"
DefaultModule mimic3-generic
```

Restart speech-dispatcher with:

``` sh
sudo systemd restart speech-dispatcher
```

and test it out with:

``` sh
spd-say 'Hello from speech dispatcher.'
```


### Systemd Service

To ensure that Mimic 3 runs at boot, create a systemd service at `$HOME/.config/systemd/user/mimic3.service` with the contents:

``` text
[Unit]
Description=Run Mimic 3 web server
Documentation=https://github.com/MycroftAI/mimic3

[Service]
ExecStart=/path/to/mimic3-server

[Install]
WantedBy=default.target
```

Make sure to change `/path/to/mimic3-server` to wherever you installed Mimic 3.

Refresh the systemd services:

``` sh
systemd --user daemon-reload
```

Now try starting the service:

``` sh
systemd --user start mimic3
```

If that's successful, ensure it starts at boot:

``` sh
systemd --user enable mimic3
```


## Architecture

Mimic 3 uses the [VITS](https://arxiv.org/abs/2106.06103), a "Conditional Variational Autoencoder with Adversarial Learning for End-to-End Text-to-Speech". VITS is a combination of the [GlowTTS duration predictor](https://arxiv.org/abs/2005.11129) and the [HiFi-GAN vocoder](https://arxiv.org/abs/2010.05646).

Our implementation is heavily based on [Jaehyeon Kim's PyTorch model](https://github.com/jaywalnut310/vits), with the addition of [Onnx runtime](https://onnxruntime.ai/) export for speed. 

![mimic 3 architecture](img/mimic3-architecture.png)


### Phoneme Ids

At a high level, Mimic 3 performs two important tasks:

1. Converting raw text to numeric input for the VITS TTS model, and
2. Using the model to transform numeric input into audio output

The second step is the same for every voice, but the first step (text to numbers) varies. There are currently three implementations of step 1, described below.


### gruut Phoneme-based Voices

Voices that use [gruut](https://github.com/rhasspy/gruut/) for phonemization.

gruut normalizes text and phonemizes words according to a lexicon, with a pre-trained grapheme-to-phoneme model used to guess unknown word pronunciations.


### eSpeak Phoneme-based Voices

Voices that use [eSpeak-ng](https://github.com/espeak-ng/espeak-ng) for phonemization (via [espeak-phonemizer](https://github.com/rhasspy/espeak-phonemizer)).

eSpeak-ng normalizes and phonemizes text using internal rules and lexicons. It supports a large number of languages, and can handle many textual forms.


### Character-based Voices

Voices whose "phonemes" are characters from an alphabet, typically with some punctuation.

For voices whose orthography (writing system) is close enough to its spoken form, character-based voices allow for skipping the phonemization step. However, these voices do not support text normalization, so numbers, dates, etc. must be written out.


### Epitran-based Voices

Voices that use [epitran](https://github.com/dmort27/epitran/) for phonemization.

epitran uses rules to generate phonetic pronunciations from text. It does not support text normalization, however, so numbers, dates, etc. must be written out.


## License

See [license file](LICENSE)
