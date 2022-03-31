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

Voices are automatically downloaded from [Github](https://github.com/MycroftAI/mimic3-voices) and stored in `${HOME}/.local/share/mimic3` (technically `${XDG_DATA_HOME}/mimic3`).


## Running


### Command-Line Tools

The `mimic3` command can be used to synthesize audio on the command line:

``` sh
mimic3 --voice 'en_UK/apope_low' 'My hovercraft is full of eels.' > hovercraft_eels.wav
```

See [voice keys](#voice-keys) for how to reference voices and speakers.

See `mimic3 --help` or the [CLI documentation](mimic3-tts/) for more details.


#### Downloading Voices

Mimic 3 automatically downloads voices when they're first used, but you can manually download them too with `mimic3-download`.

For example:

``` sh
mimic3-download 'en_US/*'
```

will download all U.S. English voices to `${HOME}/.local/share/mimic3`.

See `mimic3-download --help` for more options.


### Web Server and Client

Start a web server with `mimic3-server` and visit `http://localhost:59125` to view the web UI.

![screenshot of web interface](mimic3-http/img/server_screenshot.jpg)

The following endpoints are available:

* `/api/tts`
    * `POST` text or [SSML](#ssml) and receive WAV audio back
    * Use `?voice=` to select a different [voice/speaker](#voice-keys)
    * Set `Content-Type` to `application/ssml+xml` (or use `?ssml=1`) for [SSML](#ssml) input
* `/api/voices`
    * Returns a JSON list of available voices
    
An [OpenAPI](https://www.openapis.org/) test page is also available at `http://localhost:59125/openapi`

See `mimic3-server --help` for the [web server documentation](mimic3-http/) for more details.


#### Web Client

The `mimic3-client` program provides an interface to the Mimic 3 web server that is similar to the `mimic3` command.

Assuming you have started `mimic3-server` and can access `http://localhost:59125`, then:

``` sh
mimic3-client --voice 'en_UK/apope_low' 'My hovercraft is full of eels.' > hovercraft_eels.wav
```

See `mimic3-client --help` for more options.


## MaryTTS Compatibility

Use the Mimic 3 web server as a drop-in replacement for [MaryTTS](http://mary.dfki.de/), for example with [Home Assistant](https://www.home-assistant.io/integrations/marytts/).

Make sure to use a compatible [voice key](#voice-keys) like `en_UK/apope_low`.

For Mycroft, you can use this instead of [the plugin](https://github.com/MycroftAI/plugin-tts-mimic3) by running:


``` sh
mycroft-config edit user
```

and then adding the following:

``` json
"tts": {
"module": "marytts",
"marytts": {
    "url": "http://localhost:59125",
    "voice": "en_UK/apope_low"
}
```


## SSML

A [subset of SSML](mimic3-tts/#SSML) (Speech Synthesis Markup Language) is supported.

For example:

``` xml
<speak>
  <voice name="en_UK/apope">
    <s>
      Welcome to the world of speech synthesis.
    </s>
  </voice>
  <break time="3s" />
  <voice name="en_US/cmu-arctic#slt">
    <s>
      This is a <say-as interpret-as="number" format="ordinal">2</say-as> voice.
    </s>
  </voice>
</speak>
```

will speak the two sentences with different voices and a 3 second second pause in between. The second sentence will also have the number "2" pronounced as "second" (ordinal form).

SSML `<say-as>` support varies between voice types:

* [gruut](https://github.com/rhasspy/gruut/#ssml)
* [eSpeak-ng](http://espeak.sourceforge.net/ssml.html)
* Character-based voices do not currently support `<say-as>`


## License

See [license file](LICENSE)
