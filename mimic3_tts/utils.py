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
"""Utility methods for Mimic 3"""
import hashlib
import re
import typing
import unicodedata

import numpy as np

# Wildcard character for voice keys (e.g., en_US/*)
WILDCARD = "*"

# Language code to native/English language name
LANG_NAMES = {
    "bn": ("বাংলা", "Bengali"),
    "af_ZA": "Afrikaans",
    "da_DK": ("Dansk", "Danish"),
    "de_DE": ("Deutsch", "German"),
    "en_UK": "English (UK)",
    "en_US": "English (US)",
    "el_GR": ("Ελληνικά", "Greek"),
    "es_ES": ("Español", "Spanish"),
    "fa": ("فارسی", "Persian"),
    "fi_FI": ("Suomi", "Finnish"),
    "fr_FR": ("Français", "French"),
    "gu_IN": ("ગુજરાતી", "Gujarati"),
    "ha_NE": "Hausa",
    "hu_HU": ("Magyar Nyelv", "Hungarian"),
    "it_IT": ("Italiano", "Italian"),
    "jv_ID": ("Basa Jawa", "Javanese"),
    "ko_KO": ("한국어", "Korean"),
    "ne_NP": ("नेपाली", "Nepali"),
    "nl": ("Nederlands", "Dutch"),
    "pl_PL": ("Polski", "Polish"),
    "ru_RU": ("Русский", "Russian"),
    "sw": "Kiswahili",
    "te_IN": ("తెలుగు", "Telugu"),
    "tn_ZA": "Setswana",
    "uk_UK": ("украї́нська мо́ва", "Ukrainian"),
    "vi_VN": ("Tiếng Việt", "Vietnamese"),
    "yo": ("Èdè Yorùbá", "Yoruba"),
}

# Sample text sent with /api/voices JSON
SAMPLE_SENTENCES = {
    "bn": """রংধনু বা রামধনু বা ইন্দ্রধনু হল একটি দৃশ্যমান ধনুকাকৃতি আলোর রেখা যা
        বায়ুমণ্ডলে অবস্থিত জলকণায় সূর্যালোকের প্রতিফলন এবং প্রতিসরণের ফলে ঘটিত হয়।
        সাধারণত বৃষ্টির পর আকাশে সূর্যের বিপরীত দিকে রামধনু দেখা যায়। রংধনুতে সাতটি
        রঙের সমাহার দেখা যায়। দেখতে ধনুকের মতো বাঁকা হওয়ায় এটির নাম রংধনু।""",
    "af": """'n Reënboog is 'n boog van gekleurde lig wat ontstaan wanneer die
        son teen 'n waterdruppel skyn en die wit lig dan deur middel van
        ligbreking in die volledige kleurspektrum opgebreek word. Die middelpunt
        van die reënboog staan reg teenoor die son en die boog het 'n straal van
        ongeveer 42°. Die kleure van die reënboog is, van buite na binne, rooi,
        oranje, geel, groen, blou, indigo en violet.""",
    "da": """En regnbue er et optisk fænomen; en "lyseffekt", som skabes på
        himlen, når lys fra Solen rammer små vanddråber i luften, f.eks.
        faldende regn. Sådanne svævende vanddråber har facon omtrent som en
        kugle – jo mindre de er, desto mere perfekt kugleform har de. Disse
        kuglerunde dråber bryder, eller "afbøjer" lyset på samme måde som et
        optisk prisme ved en proces, der kaldes refraktion. Og derudover opfører
        indersiden af dråbernes overflader sig til en vis grad som små spejle,
        (et fænomen der kaldes for intern refleksion), der kaster lyset tilbage
        i nogenlunde den retning, det kom fra – det er derfor, man altid ser
        regnbuer i retningen direkte væk fra solen.""",
    "de": """Der Regenbogen ist ein atmosphärisch-optisches Phänomen, das als
        kreisbogenförmiges farbiges Lichtband in einer von der Sonne
        beschienenen Regenwand oder -wolke wahrgenommen wird. Sein radialer
        Farbverlauf ist das mehr oder weniger verweißlichte sichtbare Licht des
        Sonnenspektrums. Das Sonnenlicht wird beim Ein- und beim Austritt an
        jedem annähernd kugelförmigen Regentropfen abgelenkt und in Licht
        mehrerer Farben zerlegt.""",
    "en": """A rainbow is a meteorological phenomenon that is caused by
        reflection, refraction and dispersion of light in water droplets
        resulting in a spectrum of light appearing in the sky. It takes the form
        of a multi-colored circular arc. Rainbows caused by sunlight always
        appear in the section of sky directly opposite the Sun.""",
    "el": """Οι επιστήμονες μελετούν ακόμη το ουράνιο τόξο. Ο Καρλ Μπ. Μπόγιερ
        παρατηρεί: «Μέσα σε μια σταγόνα βροχής η αλληλεπίδραση της ενέργειας του
        φωτός με την ύλη είναι τόσο στενή ώστε οδηγούμαστε κατευθείαν στην
        κβαντομηχανική και στη θεωρία της σχετικότητας. Αν και γνωρίζουμε αρκετά
        πράγματα για το πώς σχηματίζεται το ουράνιο τόξο, λίγα είναι αυτά που
        έχουμε μάθει για το πώς γίνεται αντιληπτό».""",
    "es": """Un arcoíris​ o arco iris es un fenómeno óptico y meteorológico que
        consiste en la aparición en el cielo de un arco de luz multicolor,
        originado por la descomposición de la luz solar en el espectro visible,
        la cual se produce por refracción, cuando los rayos del sol atraviesan
        pequeñas gotas de agua contenidas en la atmósfera terrestre.""",
    "fa": """برای دیگر کاربردها رنگین‌کمان (ابهام‌زدایی) را ببینید.  رنگین‌کمان
        دوتایی و رنگین‌کمان‌های اضافی در درون کمان اصلی. سایهٔ سر عکاس مرکز دایرهٔ
        رنگین‌کمان را مشخص می‌کند (نقطهٔ پاد خورشیدی).  رنگین‌کمان پدیده‌ای نوری و
        قیاسی است که زمانی که خورشید به قطرات نم و رطوبت جو زمین می‌تابد باعث
        ایجاد طیفی از نور در آسمان می‌شود. این پدیده به شکل یک کمان رنگین در
        می‌آید.""",
    "fi": """Sateenkaari on spektrin väreissä esiintyvä ilmakehän optinen ilmiö.
        Se syntyy, kun valo taittuu pisaran etupinnasta, heijastuu pisaran
        takapinnasta ja taittuu jälleen pisaran etupinnasta. Koska vesipisara on
        dispersiivinen, valkoinen valo hajoaa väreiksi muodostaen
        sateenkaaren.""",
    "fr": """Un arc-en-ciel est un photométéore, un phénomène optique se
        produisant dans le ciel, visible dans la direction opposée au Soleil
        quand il brille pendant la pluie. C'est un arc de cercle coloré d'un
        dégradé de couleurs continu du rouge, à l'extérieur, au jaune au vert et
        au bleu, jusqu'au violet à l'intérieur.""",
    "gu": """મેઘધનુષ આકાશમાં ખાસ કરીને ચોમાસા દરમિયાન જોવા મળે છે. વરસાદના વાદળ પર
        પડતાં સૂર્યના કિરણોને કારણે આકાશમાં અર્ધગોળાકાર તેમ જ સાત રંગોનું મેઘધનુષ રચાય છે.
        મેઘધનુષમાં સૌથી ઉપર જાંબલી રંગ, પછી નીલો રંગ, પછી વાદળી રંગ, પછી લીલો રંગ, પછી
        પીળો રંગ, પછી નારંગી રંગ તેમ જ છેલ્લે લાલ રંગ એમ સાત રંગો જોવા મળે છે. ગોળાકાર
        હોવાથી તે ધનુષ જેવું દેખાય છે અને આ ગોળાકાર આકાર પૃથ્વીના ગોળ હોવાને કારણે સર્જાય
        છે.""",
    "ha": """Rainbow wani muhimmin haske ne da yake bayyana a cikin giza-gizai a
        sararin samaniya wanda zaka ga yayi lankwasa kamar misalin baka ya
        dangana daga kusurwa zuwa kusurwa. A turance ana kiransa Rainbow. Shi dai
        wannan abu yana dauke da kaloli daban-daban har kusan guda bakwai, mafi
        akasari yana bayyana ne lokacin da hadari ya taso, cikin ikon Allah da
        zarar bakan gizo ya bayyana, nan take zaka ga hadarin ya lafa ma'ana zai
        washe zuwa wani dan lokaci daga nan kuma sai Ruwa ya kece. Amma mafi
        akasari wani lokacin sam baza ma ayi ruwan ba.""",
    "hu": """A szivárvány olyan optikai jelenség, melyet eső- vagy páracseppek
        okoznak, mikor a fény prizmaszerűen megtörik rajtuk és színeire bomlik,
        kialakul a színképe, más néven spektruma. Az ív külső része vörös, míg a
        belső ibolya. Előfordul az ún. dupla szivárvány is, amelynél egy másik,
        halványabb ív is látható fordított sorrendű színekkel.""",
    "it": """In fisica dell'atmosfera e meteorologia l'arcobaleno è un fenomeno
        ottico atmosferico che produce uno spettro quasi continuo di luce nel
        cielo quando la luce del Sole attraversa le gocce d'acqua rimaste in
        sospensione dopo un temporale, o presso una cascata o una fontana. Lo
        spettro elettromagnetico dell'arcobaleno include lunghezze d'onda sia
        visibili sia non visibili all'occhio umano, queste ultime rilevabili
        attraverso uno spettrometro.""",
    "jv": """Kluwung, kuwung, wangkawa utawa éndracapa iku pratanda optik lan
        météorologi wujud cahya manéka warna jinèjèr mlengkung ing langit utawa
        papan liyané. Ing langit, kluwung katon kaya gandéwa cahya kang pucuké
        ngarah ing horizon nalika udan riwis-riwis. Kluwung uga bisa katon ing
        sacedhaké grojogan. Racaké udan anané ing wektu soré, saéngga kluwung
        katon ing sisih wétan. Déné menawa ésuk, kluwung katon ing kulon,
        diarani téja.""",
    "ko": """무지개(문화어: 색동다리)는 하늘에 보이는 호(弧)를 이루는 색 띠를
        말한다. 색 경계가 분명하지 않아 각 문화권마다 색의 개수가 다르게
        인식되기도 한다.  대부분 지표로부터 하늘에 걸쳐서 나타나는 반원형 고리
        모양으로 나타난다.  공기 중에 떠 있는 수많은 물방울에 햇빛이나 달빛
        이닿아 물방울 안에서 굴절과 반사가 일어날 때, 물방울이 프리즘과 같은
        작용을 하여 분산되어 나타나는 현상이다.  세계에서 가장 오랫동안 관측된
        무지개는 2017년 11월 27일 중화민국 타이베이에서 관측된 것으로, 9시간
        내내 무지개가 떠올랐다.""",
    "ne": """इन्द्रेणी वा इन्द्रधनुष प्रकाश र रंगबाट उत्पन्न भएको यस्तो घटना हो जसमा रंगीन
        प्रकाशको एउटा अर्धवृत आकाशमा देखिन्छ। जब सूर्यको प्रकाश पृथ्वीको वायुमण्डलमा भएको
        पानीको थोपा माथि पर्छ, पानीको थोपाले प्रकाशलाई परावर्तन, आवर्तन र डिस्पर्सन
        गर्दछ। फलस्वरुप आकाशमा एउटा सप्तरङ्गी अर्धवृताकार प्रकाशीय आकृति उत्पन्न हुन्छ। यो
        आकृतिलाई नै इन्द्रेणी भनिन्छ। इन्द्रेणी देखिनुको कारण वायुमण्डलमा पानीका कणहरु हुनु नै
        हो। वर्षा, झरनाबाट उछिट्टिएको पानी, शीत, कुहिरो आदिको इन्द्रेणी देखिने प्रक्रियामा
        महत्त्वपूर्ण भूमिका हुन्छ। इन्द्रेणीमा सात रंगहरु रातो, सुन्तला, पहेंलो, हरियो, आकाशे
        निलो, गाढा निलो र बैजनी रंग क्रमैसँग देखिन्छ। यसमा सबैभन्दा माथिल्लो छेउमा रातो रंग
        र अर्को छेउमा बैजनी रंग देखिन्छ। इन्द्रेणी पूर्ण वृत्ताकार समेत हुन सक्ने भए पनि साधरण
        अवलोकनकर्ताले जमिन माथि बनेको आधा भाग मात्र देख्न सकिन्छ ।""",
    "nl": """Een regenboog is een gekleurde cirkelboog die aan de hemel
        waargenomen kan worden als de, laagstaande, zon tegen een nevel van
        waterdruppeltjes aan schijnt en de zon zich achter de waarnemer bevindt.
        Het is een optisch effect dat wordt veroorzaakt door de breking en
        weerspiegeling van licht in de waterdruppels.""",
    "pl": """Tęcza, zjawisko optyczne i meteorologiczne, występujące w postaci
        charakterystycznego wielobarwnego łuku powstającego w wyniku
        rozszczepienia światła widzialnego, zwykle promieniowania słonecznego,
        załamującego się i odbijającego wewnątrz licznych kropli wody mających
        kształt zbliżony do kulistego.  Rozszczepienie światła jest wynikiem
        zjawiska dyspersji, powodującego różnice w kącie załamania światła o
        różnej długości fali przy przejściu z powietrza do wody i z wody do
        powietrza.""",
    "pt": """Um arco-íris, também popularmente denominado arco-da-velha, é um
        fenômeno óptico e meteorológico que separa a luz do sol em seu espectro
        contínuo quando o sol brilha sobre gotículas de água suspensas no ar. É
        um arco multicolorido com o vermelho em seu exterior e o violeta em seu
        interior. Por ser um espectro de dispersão da luz branca, o arco-íris
        contém uma quantidade infinita de cores sem qualquer delimitação entre
        elas.""",
    "ru": """Ра́дуга, атмосферное, оптическое и метеорологическое явление,
        наблюдаемое при освещении ярким источником света множества водяных
        капель.  Радуга выглядит как разноцветная дуга или окружность,
        составленная из цветов спектра видимого излучения. Это те семь цветов,
        которые принято выделять в радуге в русской культуре, но следует иметь в
        виду, что на самом деле спектр непрерывен, и его цвета плавно переходят
        друг в друга через множество промежуточных оттенков.""",
    "sv": """En regnbåge är ett optiskt, meteorologiskt fenomen som uppträder som
        ett fullständigt ljusspektrum i form av en båge på himlen då solen lyser
        på nedfallande regn. Regnbågen består färgmässigt av en kontinuerlig
        övergång från rött via gula, gröna och blå nyanser till violett innerst;
        ofta definieras antalet färger som sju, inklusive orange och indigo.""",
    "sw": """Upinde wa mvua ni tao la rangi mbalimbali angani ambalo linaweza
        kuonekana wakati Jua huangaza kupitia matone ya mvua inayoanguka. Mfano
        wa rangi hizo huanza na nyekundu nje na hubadilika kupitia rangi ya
        chungwa, njano, kijani, bluu, na urujuani ndani. Rangi hizi na ufuatano
        ni sehemu ya spektra ya nuru. Upinde wa mvua huundwa wakati mwanga
        umepinda ukiingia matone ya maji, umegawanyika kuwa rangi tofauti, na
        kurudishwa nyuma. Hapa spektra ya nuru inayoonekana ambayo sisi tunaona
        kwa macho kama nyeupe tu.""",
    "te": """ఇంద్ర ధనుస్సు దృష్టి విద్యా సంబంధమయిన వాతావరణ శాస్త్ర సంబంధమయిన దృగ్విషయం. అది
        నీటిబిందువులపై కాంతి పరావర్తనం, వక్రీభవనం ద్వారా సంబవిస్తుంది. అది ఆకాశంలో రంగురంగుల చాపం
        రూపంలో ఉంటుంది. ఈ చర్య వల్ల రశ్మి వాతావరణం లోని నీటి బిందువులతో అంతఃపరావర్తనం చెంది,
        వర్ణానుసారం విచ్ఛిన్నమయి ఏడు రంగులుగా మారుతుంది. అది ఒక అర్ధవృత్తాకారంలో రెండు అంచులూ భూమిలో
        ఉన్నట్టు, వృత్తాకారం ఆకాశం వైపుకున్నట్టు గోచరిస్తుంది.  సూర్యరశ్మి ద్వారా తయారయ్యే ఇంద్రధనుస్సు,
        ఎల్లపుడూ సూర్యునికి వ్యతిరేక దిశలోనే కనిపిస్తుంది. ఇక రంగుల అమరికను బట్టీ ఇంద్రధనుస్సుని
        రెండు రకాలుగా చెప్పొచ్చు. ఒకటి - ప్రాథమిక ఇంద్రధనుస్సు; రెండు ద్వితీయ ఇంద్రధనుస్సు. మొదటి
        ఇంద్రధనుస్సులో వృత్తం పై భాగంలో ఎరుపు,, లోపలి భాగంలో ఊదా రంగులో ఉంటాయి.""",
    "tn": """Batho botlhe ba tsetswe ba gololosegile le go lekalekana ka seriti
        le ditshwanelo. Ba abetswe go akanya le maikutlo, mme ba tshwanetse go
        direlana ka mowa wa bokaulengwe.""",
    "uk": """Весе́лка, також ра́йдуга оптичне явище в атмосфері, що являє собою
        одну, дві чи декілька різнокольорових дуг (або кіл, якщо дивитися з
        повітря), що спостерігаються на тлі хмари, якщо вона розташована проти
        Сонця. Червоний колір ми бачимо з зовнішнього боку первинної веселки, а
        фіолетовий — із внутрішнього.""",
    "vi": """Cầu vồng hay mống cũng như quang phổ là hiện tượng tán sắc của các
    ánh sáng từ Mặt Trời khi khúc xạ và phản xạ qua các giọt nước mưa. Ở nhiều
    nền văn hóa khác nhau, cầu vồng xuất hiện được coi là mang đến điềm lành cho
    nhân thế.""",
    "yo": """E̟nì kò̟ò̟kan ló ní è̟tó̟ láti kó̟ è̟kó̟. Ó kéré tán, è̟kó̟ gbo̟dò̟ jé̟ ò̟fé̟ ní
    àwo̟n ilé-è̟kó̟ alákò̟ó̟bè̟rè̟. E̟kó̟ ní ilé-è̟kó̟ alákò̟ó̟bè̟rè̟ yìí sì gbo̟dò̟ jé̟ dandan. A
    gbo̟dò̟ pèsè è̟kó̟ is̟é̟-o̟wó̟, àti ti ìmò̟-è̟ro̟ fún àwo̟n ènìyàn lápapò̟. Àn fàní tó
    dó̟gba ní ilé-è̟kó̟ gíga gbo̟dò̟ wà ní àró̟wó̟tó gbogbo e̟ni tó bá tó̟ sí.""",
}


def audio_float_to_int16(
    audio: np.ndarray, max_wav_value: float = 32767.0
) -> np.ndarray:
    """Normalize audio and convert to int16 range"""
    audio_norm = audio * (max_wav_value / max(0.01, np.max(np.abs(audio))))
    audio_norm = np.clip(audio_norm, -max_wav_value, max_wav_value)
    audio_norm = audio_norm.astype("int16")
    return audio_norm


def wildcard_to_regex(template: str, wildcard: str = "*") -> re.Pattern:
    """Convert a string with wildcards into a regex pattern"""
    wildcard_escaped = re.escape(wildcard)

    pattern_parts = ["^"]
    for i, template_part in enumerate(re.split(f"({wildcard_escaped})", template)):
        if (i % 2) == 0:
            # Fixed string
            pattern_parts.append(re.escape(template_part))
        else:
            # Wildcard separator
            pattern_parts.append(".*")

    pattern_parts.append("$")
    pattern_str = "".join(pattern_parts)

    return re.compile(pattern_str)


def file_sha256_sum(fp: typing.BinaryIO, block_bytes: int = 4096) -> str:
    """Return the sha256 sum of a (possibly large) file"""
    current_hash = hashlib.sha256()

    # Read in blocks in case file is very large
    block = fp.read(block_bytes)
    while len(block) > 0:
        current_hash.update(block)
        block = fp.read(block_bytes)

    return current_hash.hexdigest()


def to_codepoints(s: str) -> typing.List[str]:
    """Split string into a list of codepoints"""
    return list(unicodedata.normalize("NFC", s))
