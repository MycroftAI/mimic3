# Mimic 3 Web Server

A small HTTP web server for the [Mimic 3](https://github.com/MycroftAI/mimic3) text to speech system.

[Available voices](https://github.com/MycroftAI/mimic3-voices)


## Installation


## Running the Server

``` sh

```


## Endpoints

* `/api/tts`
    * `POST` text or [SSML](#ssml) and receive WAV audio back
    * Use `?voice=` to select a different [voice/speaker](#voice-keys)
    * Set `Content-Type` to `application/ssml+xml` (or use `?ssml=1`) for [SSML](#ssml) input
* `/api/voices`
    * Returns a JSON list of available voices

An [OpenAPI](https://www.openapis.org/) test page is also available at `http://localhost:59125/openapi`

## Running the Client

