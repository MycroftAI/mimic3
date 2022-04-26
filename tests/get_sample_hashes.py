#!/usr/bin/env python3
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
"""
Generates sha256 hashs of audio samples for all languages/voices.
"""
import argparse
import contextlib
import functools
import hashlib
import logging
import re
import tempfile
import typing
from multiprocessing import Pool
from pathlib import Path

from mimic3_tts import Mimic3Settings, Mimic3TextToSpeechSystem, Voice

# -----------------------------------------------------------------------------

_TEST_SENTENCES = {
    "af": """'n Reënboog is 'n boog van gekleurde lig wat ontstaan wanneer die
        son teen 'n waterdruppel skyn en die wit lig dan deur middel van
        ligbreking in die volledige kleurspektrum opgebreek word.""",
    "de": """Der Regenbogen ist ein atmosphärisch-optisches Phänomen, das als
        kreisbogenförmiges farbiges Lichtband in einer von der Sonne
        beschienenen Regenwand oder -wolke wahrgenommen wird.""",
    "en": """A rainbow is a meteorological phenomenon that is caused by
        reflection, refraction and dispersion of light in water droplets
        resulting in a spectrum of light appearing in the sky.""",
    "el": """Οι επιστήμονες μελετούν ακόμη το ουράνιο τόξο.""",
    "es": """Un arcoíris​ o arco iris es un fenómeno óptico y meteorológico que
        consiste en la aparición en el cielo de un arco de luz multicolor,
        originado por la descomposición de la luz solar en el espectro visible,
        la cual se produce por refracción, cuando los rayos del sol atraviesan
        pequeñas gotas de agua contenidas en la atmósfera terrestre.""",
    "fa": """برای دیگر کاربردها رنگین‌کمان (ابهام‌زدایی) را ببینید.""",
    "fi": """Sateenkaari on spektrin väreissä esiintyvä ilmakehän optinen ilmiö.""",
    "fr": """Un arc-en-ciel est un photométéore, un phénomène optique se
        produisant dans le ciel, visible dans la direction opposée au Soleil
        quand il brille pendant la pluie.""",
    "hu": """A szivárvány olyan optikai jelenség, melyet eső- vagy páracseppek
        okoznak, mikor a fény prizmaszerűen megtörik rajtuk és színeire bomlik,
        kialakul a színképe, más néven spektruma.""",
    "it": """In fisica dell'atmosfera e meteorologia l'arcobaleno è un fenomeno
        ottico atmosferico che produce uno spettro quasi continuo di luce nel
        cielo quando la luce del Sole attraversa le gocce d'acqua rimaste in
        sospensione dopo un temporale, o presso una cascata o una fontana.""",
    "ko": """무지개(문화어: 색동다리)는 하늘에 보이는 호(弧)를 이루는 색 띠를 말한다.""",
    "nl": """Een regenboog is een gekleurde cirkelboog die aan de hemel
        waargenomen kan worden als de, laagstaande, zon tegen een nevel van
        waterdruppeltjes aan schijnt en de zon zich achter de waarnemer bevindt.""",
    "pl": """Tęcza, zjawisko optyczne i meteorologiczne, występujące w postaci
        charakterystycznego wielobarwnego łuku powstającego w wyniku
        rozszczepienia światła widzialnego, zwykle promieniowania słonecznego,
        załamującego się i odbijającego wewnątrz licznych kropli wody mających
        kształt zbliżony do kulistego.""",
    "pt": """Um arco-íris, também popularmente denominado arco-da-velha, é um
        fenômeno óptico e meteorológico que separa a luz do sol em seu espectro
        contínuo quando o sol brilha sobre gotículas de água suspensas no ar.""",
    "ru": """Ра́дуга, атмосферное, оптическое и метеорологическое явление,
        наблюдаемое при освещении ярким источником света множества водяных
        капель.""",
    "sv": """En regnbåge är ett optiskt, meteorologiskt fenomen som uppträder som
        ett fullständigt ljusspektrum i form av en båge på himlen då solen lyser
        på nedfallande regn.""",
    "sw": """Upinde wa mvua ni tao la rangi mbalimbali angani ambalo linaweza
        kuonekana wakati Jua huangaza kupitia matone ya mvua inayoanguka.""",
    "te": """ఇంద్ర ధనుస్సు దృష్టి విద్యా సంబంధమయిన వాతావరణ శాస్త్ర సంబంధమయిన దృగ్విషయం.""",
    "tn": """Batho botlhe ba tsetswe ba gololosegile le go lekalekana ka seriti
        le ditshwanelo. Ba abetswe go akanya le maikutlo, mme ba tshwanetse go
        direlana ka mowa wa bokaulengwe.""",
    "uk": """Весе́лка, також ра́йдуга оптичне явище в атмосфері, що являє собою
        одну, дві чи декілька різнокольорових дуг (або кіл, якщо дивитися з
        повітря), що спостерігаються на тлі хмари, якщо вона розташована проти
        Сонця. Червоний колір ми бачимо з зовнішнього боку первинної веселки, а
        фіолетовий — із внутрішнього.""",
    "vi": """Cầu vồng hay mống cũng như quang phổ là hiện tượng tán sắc của các
    ánh sáng từ Mặt Trời khi khúc xạ và phản xạ qua các giọt nước mưa.""",
    "yo": """E̟nì kò̟ò̟kan ló ní è̟tó̟ láti kó̟ è̟kó̟.""",
}

_LOGGER = logging.getLogger("get_samples")

# -----------------------------------------------------------------------------


def synthesize(
    output_dir: Path, voice: Voice, args: argparse.Namespace
) -> typing.Iterable[str]:
    """Generate samples for voice in a separate process"""
    tts = Mimic3TextToSpeechSystem(
        Mimic3Settings(
            length_scale=1.0,
            noise_scale=0.0,
            noise_w=0.0,
            use_deterministic_compute=True,
            no_download=args.no_download,
        )
    )

    key = voice.key
    language = voice.language

    # Try en_US and en
    text = _TEST_SENTENCES.get(language, _TEST_SENTENCES.get(language.split("_")[0]))

    assert text, f"No sentences for {language}"

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    voice_dir = output_dir / key
    voice_dir.mkdir(parents=True, exist_ok=True)

    results = []

    # First speaker only
    voice_key = key
    sample_path = voice_dir / "sample.wav"

    if not sample_path.is_file():
        tts.voice = voice_key
        wav_bytes = tts.text_to_wav(text)
        sample_path.write_bytes(wav_bytes)

    wav_hash = hashlib.sha256(sample_path.read_bytes()).hexdigest()
    _LOGGER.info(sample_path)

    results.append(f"{voice_key} {wav_hash}")

    return results


# -----------------------------------------------------------------------------


def main():
    """Generate WAV samples from Mimic 3 in deterministic mode for testing"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", help="Directory to write samples")
    parser.add_argument(
        "--no-download", action="store_true", help="Don't download voices"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = contextlib.nullcontext()
    else:
        # Output to temp directory
        temp_dir = tempfile.TemporaryDirectory()
        output_dir = Path(temp_dir.name)

    tts = Mimic3TextToSpeechSystem(Mimic3Settings())

    # -------------------------------------------------------------------------
    # Generate samples
    # -------------------------------------------------------------------------

    with temp_dir, Pool() as pool:
        voices = sorted(tts.get_voices(), key=lambda v: v.key)
        for results in pool.map(
            functools.partial(synthesize, output_dir, args), voices
        ):
            for result in results:
                print(result)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
