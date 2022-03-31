# Mimic 3

A fast and local neural text to speech system for [Mycroft](https://mycroft.ai/) and the [Mark II](https://mycroft.ai/product/mark-ii/).

[Available voices](https://github.com/MycroftAI/mimic3-voices)


## Dependencies

Mimic 3 requires:

* Python 3.7 or higher
* The [Onnx runtime](https://onnxruntime.ai/)
* [gruut](https://github.com/rhasspy/gruut) or [eSpeak-ng](https://github.com/espeak-ng/espeak-ng) (depending on the voice)


## Installation


### eSpeak

Some voices depend on [eSpeak-ng](https://github.com/espeak-ng/espeak-ng), specifically `libespeak-ng.so`. For those voices, make sure that libespeak-ng is installed with:

``` sh
sudo apt-get install libespeak-ng1
```

### Mycroft TTS Plugin

Install the plugin:

``` sh
mycroft-pip install plugin-tts-mimic3[all]
```

Enable the plugin in your [mycroft.conf](https://mycroft-ai.gitbook.io/docs/using-mycroft-ai/customizations/mycroft-conf) file:

``` sh
mycroft-conf set tts.module mimic3_tts_plug
```

See the [plugin's documentation](https://github.com/MycroftAI/plugin-tts-mimic3) for more options.


### Using pip

Install the command-line tool:

``` sh
pip install mimic3[all]
```

Once installed, the following commands will be available:
    * `mimic3`
    * `mimic3-download`

Install the HTTP web server:

``` sh
pip install mimic3-http[all]
```

Once installed, the following commands will be available:
    * `mimic3-server`
    * `mimic3-client`

Language support can be selectively installed by replacing `all` with:

* `de` - German
* `es` - Spanish
* `fr` - French
* `it` - Italian
* `nl` - Dutch
* `ru` - Russian
* `sw` - Kiswahili

Excluding `[..]` entirely will install support for English only.


### From Source

Clone the repository:

``` sh
git clone https://github.com/MycroftAI/mimic3.git
```

Run the install script:

``` sh
cd mimic3/
./install.sh
```

A virtual environment will be created in `mimic3/.venv` and each of the Python modules will be installed in editiable mode (`pip install -e`).

Once installed, the following commands will be available in `.venv/bin`:
    * `mimic3`
    * `mimic3-server`
    * `mimic3-client`
    * `mimic3-download`


## Voice Keys

Mimic 3 references voices with the format:

* `<language>/<name>_<quality>` for single speaker voices, and
* `<language>/<name>_<quality>#<speaker>` for multi-speaker voices 
    * `<speaker>` can be a name or number starting at 0
    * Speaker names come from a voice's `speakers.txt` file
    
For example, the default [Alan Pope](https://popey.me/) voice key is `en_UK/apope_low`. The [CMU Arctic voice](https://github.com/MycroftAI/mimic3-voices/tree/master/voices/en_US/cmu-arctic_low) contains multiple speakers, with a commonly used voice being `en_US/cmu-arctic_low#slt`.

Voices are automatically downloaded from [Github](https://github.com/MycroftAI/mimic3-voices) and stored in `${HOME}/.local/share/mimic3`


## Running


### Command-Line Tools

The `mimic3` command can be used to synthesize audio on the command line:

``` sh
mimic3 --voice 'en_UK/apope_low' 'My hovercraft is full of eels.' > hovercraft_eels.wav
```

See [voice keys](#voice-keys) for how to reference voices and speakers.

See `mimic3 --help` or the [CLI documentation](mimic3-tts/README.md) for more details.


### Web Server and Client


## SSML

A [subset of SSML](mimic3-tts/README.md#SSML) is supported.


## License

See [license file](LICENSE)
