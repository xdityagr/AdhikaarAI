"""
Translations.

Five languages, chosen by SC population rather than convenience: Hindi, English,
Marathi, Bengali and Tamil. Doing five properly beats claiming twenty-two.

Two rules that keep this honest:

1. NUMBERS ARE NEVER TRANSLATED, only formatted. Rupee figures come from the
   calculator and pass through untouched, so a translation bug can never change
   what a loan costs.

2. SCHEME NAMES STAY IN ENGLISH. "Micro Finance Scheme" is what is printed on the
   form at the branch counter. Translating it would help nobody at the window.

Script detection is a Unicode lookup, not a model — PRD-v3 §6.5's guess-then-
confirm approach. Someone who types देवनागरी should never be shown a language
menu in English first.
"""

from __future__ import annotations

from typing import Optional

DEFAULT_LANGUAGE = "en"

# The thirteen languages the interface offers, which are the languages
# myScheme itself publishes scheme text in — verified against their API, not
# assumed.
#
# The scripted conversation below is written in the first five. For the other
# eight `t()` falls back to English, which is a real gap and is stated rather
# than hidden: the model-backed assistant answers in whichever of the thirteen
# a person writes in, so the fallback only affects the no-API-key path.
LANGUAGES: dict[str, dict[str, str]] = {
    "en": {"name": "English", "native": "English", "scripted": True},
    "hi": {"name": "Hindi", "native": "हिन्दी", "scripted": True},
    "mr": {"name": "Marathi", "native": "मराठी", "scripted": True},
    "bn": {"name": "Bengali", "native": "বাংলা", "scripted": True},
    "ta": {"name": "Tamil", "native": "தமிழ்", "scripted": True},
    "te": {"name": "Telugu", "native": "తెలుగు", "scripted": False},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી", "scripted": False},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ", "scripted": False},
    "ml": {"name": "Malayalam", "native": "മലയാളം", "scripted": False},
    "pa": {"name": "Punjabi", "native": "ਪੰਜਾਬੀ", "scripted": False},
    "or": {"name": "Odia", "native": "ଓଡ଼ିଆ", "scripted": False},
    "as": {"name": "Assamese", "native": "অসমীয়া", "scripted": False},
    "ur": {"name": "Urdu", "native": "اردو", "scripted": False},
}

# Unicode blocks -> language. Devanagari is genuinely ambiguous (Hindi/Marathi),
# so it resolves to Hindi and the user can switch in one tap; everything else
# maps cleanly.
_SCRIPT_RANGES: list[tuple[int, int, str]] = [
    (0x0900, 0x097F, "hi"),   # Devanagari — Hindi or Marathi
    (0x0980, 0x09FF, "bn"),   # Bengali — also Assamese, see below
    (0x0A00, 0x0A7F, "pa"),   # Gurmukhi — Punjabi
    (0x0A80, 0x0AFF, "gu"),   # Gujarati
    (0x0B00, 0x0B7F, "or"),   # Odia
    (0x0B80, 0x0BFF, "ta"),   # Tamil
    (0x0C00, 0x0C7F, "te"),   # Telugu
    (0x0C80, 0x0CFF, "kn"),   # Kannada
    (0x0D00, 0x0D7F, "ml"),   # Malayalam
    (0x0600, 0x06FF, "ur"),   # Arabic script — Urdu here
    (0x0750, 0x077F, "ur"),   # Arabic Supplement
]

# Two scripts are shared, and a share cannot be resolved by code point alone.
#
# Bengali and Assamese use the same block, differing in two letters; Devanagari
# carries both Hindi and Marathi. Guessing wrong is cheap — the reader switches
# in one tap — but guessing at all beats making someone choose a language before
# they are allowed to ask a question. The more widely read of each pair wins.
_AMBIGUOUS_SCRIPTS = {"hi": ("hi", "mr"), "bn": ("bn", "as")}

# Assamese-specific letters: ৰ (ra) and ৱ (va), which Bengali does not use.
_ASSAMESE_MARKERS = "ৰৱ"


def detect_language(text: str) -> Optional[str]:
    """Guess a language from the script used. None when it's plain ASCII.

    Free, deterministic, no model, and it runs on the very first message — which
    is the whole point: nobody should have to pick a language before they can ask
    a question.
    """
    if not text:
        return None
    counts: dict[str, int] = {}
    for char in text:
        code = ord(char)
        for lo, hi, lang in _SCRIPT_RANGES:
            if lo <= code <= hi:
                counts[lang] = counts.get(lang, 0) + 1
                break
    if not counts:
        return None
    best = max(counts, key=counts.get)

    # Assamese and Bengali share a block; two letters tell them apart.
    if best == "bn" and any(ch in _ASSAMESE_MARKERS for ch in text):
        return "as"
    return best


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

STRINGS: dict[str, dict[str, str]] = {
    # ---- greeting and intake ----
    "greet": {
        "en": "Namaste. I can find the government schemes you are entitled to — housing, pension, scholarship, medical help, a business loan — explain what each really gives you, and point you to an office that can actually process it. It takes about a minute.",
        "hi": "नमस्ते। मैं वे सरकारी योजनाएँ ढूँढ सकता हूँ जिनका आपको हक़ है — घर, पेंशन, छात्रवृत्ति, इलाज की मदद, कारोबार का ऋण — बता सकता हूँ कि हर एक से असल में क्या मिलेगा, और वह दफ़्तर बता सकता हूँ जो सचमुच काम कर सके। इसमें लगभग एक मिनट लगेगा।",
        "mr": "नमस्कार. तुमचा हक्क असलेल्या सरकारी योजना मी शोधू शकतो — घर, निवृत्तिवेतन, शिष्यवृत्ती, वैद्यकीय मदत, व्यवसाय कर्ज — प्रत्येकातून प्रत्यक्षात काय मिळते ते सांगू शकतो, आणि जे कार्यालय खरोखर काम करू शकते ते सुचवू शकतो. यास सुमारे एक मिनिट लागेल.",
        "bn": "নমস্কার। আপনার প্রাপ্য সরকারি প্রকল্প আমি খুঁজে দিতে পারি — বাসস্থান, পেনশন, বৃত্তি, চিকিৎসার সাহায্য, ব্যবসার ঋণ — প্রতিটি থেকে আসলে কী মেলে তা বুঝিয়ে দিতে পারি, আর কোন দপ্তর সত্যিই কাজ করবে তা বলে দিতে পারি। প্রায় এক মিনিট লাগবে।",
        "ta": "வணக்கம். உங்களுக்கு உரிய அரசுத் திட்டங்களை நான் கண்டறிய முடியும் — வீடு, ஓய்வூதியம், உதவித்தொகை, மருத்துவ உதவி, தொழில் கடன் — ஒவ்வொன்றிலும் உண்மையில் என்ன கிடைக்கும் என்பதை விளக்கி, உண்மையில் செயல்படுத்தக்கூடிய அலுவலகத்தையும் சொல்ல முடியும். ஒரு நிமிடம் ஆகும்.",
    },
    "ask_need": {
        "en": "What do you need help with?",
        "hi": "आपको किस चीज़ में मदद चाहिए?",
        "mr": "तुम्हाला कशासाठी मदत हवी?",
        "bn": "আপনার কীসে সাহায্য দরকার?",
        "ta": "உங்களுக்கு எதற்கு உதவி வேண்டும்?",
    },
    "need_business": {
        "en": "Money for a business", "hi": "कारोबार के लिए पैसा",
        "mr": "व्यवसायासाठी पैसा", "bn": "ব্যবসার জন্য টাকা", "ta": "தொழிலுக்குப் பணம்",
    },
    "need_study": {
        "en": "Studies or a scholarship", "hi": "पढ़ाई या छात्रवृत्ति",
        "mr": "शिक्षण किंवा शिष्यवृत्ती", "bn": "পড়াশোনা বা বৃত্তি", "ta": "படிப்பு அல்லது உதவித்தொகை",
    },
    "need_housing": {
        "en": "A house or repairs", "hi": "घर या मरम्मत",
        "mr": "घर किंवा दुरुस्ती", "bn": "বাড়ি বা মেরামত", "ta": "வீடு அல்லது பழுது",
    },
    "need_pension": {
        "en": "Pension or monthly support", "hi": "पेंशन या मासिक सहायता",
        "mr": "निवृत्तिवेतन किंवा मासिक मदत", "bn": "পেনশন বা মাসিক সহায়তা", "ta": "ஓய்வூதியம் அல்லது மாத உதவி",
    },
    "need_health": {
        "en": "Treatment or health cover", "hi": "इलाज या स्वास्थ्य बीमा",
        "mr": "उपचार किंवा आरोग्य विमा", "bn": "চিকিৎসা বা স্বাস্থ্য বিমা", "ta": "சிகிச்சை அல்லது மருத்துவக் காப்பீடு",
    },
    "need_job": {
        "en": "Work or training", "hi": "काम या प्रशिक्षण",
        "mr": "काम किंवा प्रशिक्षण", "bn": "কাজ বা প্রশিক্ষণ", "ta": "வேலை அல்லது பயிற்சி",
    },
    "need_farming": {
        "en": "Farming or land", "hi": "खेती या ज़मीन",
        "mr": "शेती किंवा जमीन", "bn": "চাষ বা জমি", "ta": "விவசாயம் அல்லது நிலம்",
    },
    "need_everything": {
        "en": "Show me everything", "hi": "मुझे सब दिखाइए",
        "mr": "मला सर्व दाखवा", "bn": "আমাকে সব দেখান", "ta": "எல்லாவற்றையும் காட்டு",
    },
    "welfare_intro": {
        "en": "Here is what you may be entitled to. Nothing here is decided by a computer guessing — each one matched a published rule.",
        "hi": "यह रहा जिसका आपको हक़ हो सकता है। यहाँ कुछ भी कंप्यूटर के अंदाज़े से तय नहीं हुआ — हर एक किसी प्रकाशित नियम पर खरा उतरा है।",
        "mr": "तुमचा हक्क असू शकतो ते हे आहे. इथे काहीही संगणकाच्या अंदाजाने ठरलेले नाही — प्रत्येक प्रकाशित नियमावर उतरले आहे.",
        "bn": "আপনার প্রাপ্য হতে পারে এমন কিছু এখানে। এখানে কিছুই কম্পিউটারের অনুমানে ঠিক হয়নি — প্রতিটিই কোনও প্রকাশিত নিয়মে মিলেছে।",
        "ta": "உங்களுக்கு உரியதாக இருக்கக்கூடியவை இவை. இங்கு எதுவும் கணினியின் ஊகத்தால் தீர்மானிக்கப்படவில்லை — ஒவ்வொன்றும் வெளியிடப்பட்ட விதியுடன் பொருந்தியது.",
    },
    "welfare_note": {
        "en": "Each scheme has conditions in its full text that we have not read, so treat these as likely, not certain. Open a scheme to see its own rules before you travel.",
        "hi": "हर योजना के पूरे पाठ में कुछ शर्तें होती हैं जो हमने नहीं पढ़ीं, इसलिए इन्हें संभावित मानिए, पक्का नहीं। जाने से पहले योजना खोलकर उसके अपने नियम देख लीजिए।",
        "mr": "प्रत्येक योजनेच्या संपूर्ण मजकुरात आम्ही न वाचलेल्या अटी असतात, म्हणून या संभाव्य माना, निश्चित नाही. जाण्यापूर्वी योजना उघडून तिचे नियम पहा.",
        "bn": "প্রতিটি প্রকল্পের পূর্ণ পাঠে এমন শর্ত থাকে যা আমরা পড়িনি, তাই এগুলিকে সম্ভাব্য ধরুন, নিশ্চিত নয়। যাওয়ার আগে প্রকল্প খুলে তার নিয়ম দেখে নিন।",
        "ta": "ஒவ்வொரு திட்டத்தின் முழு உரையிலும் நாங்கள் படிக்காத நிபந்தனைகள் உள்ளன; எனவே இவற்றை வாய்ப்புள்ளவை என்று கொள்ளுங்கள், உறுதி அல்ல. செல்வதற்கு முன் திட்டத்தைத் திறந்து அதன் விதிகளைப் பாருங்கள்.",
    },
    "welfare_none": {
        "en": "Nothing matched every answer. Usually one answer is narrower than it needs to be — try 'Show me everything', or change your state.",
        "hi": "हर जवाब से कुछ मेल नहीं खाया। आमतौर पर कोई एक जवाब ज़रूरत से ज़्यादा सीमित होता है — 'मुझे सब दिखाइए' आज़माइए, या अपना राज्य बदलिए।",
        "mr": "प्रत्येक उत्तराशी काहीच जुळले नाही. सहसा एखादे उत्तर गरजेपेक्षा मर्यादित असते — 'मला सर्व दाखवा' वापरून पहा, किंवा राज्य बदला.",
        "bn": "প্রতিটি উত্তরের সঙ্গে কিছুই মেলেনি। সাধারণত একটি উত্তর দরকারের চেয়ে সংকীর্ণ — 'আমাকে সব দেখান' চেষ্টা করুন, বা রাজ্য বদলান।",
        "ta": "எல்லாப் பதில்களுடனும் எதுவும் பொருந்தவில்லை. பொதுவாக ஒரு பதில் தேவைக்கு அதிகமாகக் குறுகியது — 'எல்லாவற்றையும் காட்டு' முயலுங்கள், அல்லது மாநிலத்தை மாற்றுங்கள்.",
    },
    "ask_purpose": {
        "en": "What do you need the money for?",
        "hi": "आपको पैसे किस काम के लिए चाहिए?",
        "mr": "तुम्हाला पैसे कशासाठी हवे आहेत?",
        "bn": "আপনার টাকা কী কাজে লাগবে?",
        "ta": "உங்களுக்கு எதற்காகப் பணம் தேவை?",
    },
    "opt_business": {
        "en": "Start or grow a business", "hi": "काम या दुकान शुरू करने के लिए",
        "mr": "व्यवसाय सुरू करण्यासाठी", "bn": "ব্যবসা শুরু করতে", "ta": "தொழில் தொடங்க",
    },
    "opt_education": {
        "en": "Study or a course", "hi": "पढ़ाई या कोर्स के लिए",
        "mr": "शिक्षणासाठी", "bn": "পড়াশোনার জন্য", "ta": "படிப்புக்காக",
    },
    "ask_cost": {
        "en": "Roughly how much will it cost to set up? A rough figure is fine.",
        "hi": "इसे शुरू करने में लगभग कितना खर्च आएगा? अंदाज़ा बता दीजिए।",
        "mr": "हे सुरू करण्यासाठी अंदाजे किती खर्च येईल? अंदाजे रक्कम सांगा.",
        "bn": "এটি শুরু করতে আনুমানিক কত খরচ হবে? আনুমানিক অঙ্কই যথেষ্ট।",
        "ta": "இதைத் தொடங்க தோராயமாக எவ்வளவு செலவாகும்? தோராயமான தொகை போதும்.",
    },
    "ask_income": {
        "en": "And your family's total income in a year — everyone in the household added together, not just you.",
        "hi": "और आपके पूरे परिवार की साल भर की आमदनी — घर के सब लोगों की मिलाकर, सिर्फ़ आपकी नहीं।",
        "mr": "आणि तुमच्या संपूर्ण कुटुंबाचे वर्षभराचे उत्पन्न — घरातील सर्वांचे मिळून, फक्त तुमचे नाही.",
        "bn": "এবং আপনার পরিবারের এক বছরের মোট আয় — বাড়ির সবার মিলিয়ে, শুধু আপনার নয়।",
        "ta": "உங்கள் குடும்பத்தின் ஒரு வருட மொத்த வருமானம் — வீட்டில் உள்ள அனைவரும் சேர்த்து, உங்களுடையது மட்டும் அல்ல.",
    },
    "ask_category": {
        "en": "Which category do you belong to?",
        "hi": "आप किस वर्ग से हैं?",
        "mr": "तुम्ही कोणत्या प्रवर्गातील आहात?",
        "bn": "আপনি কোন শ্রেণিভুক্ত?",
        "ta": "நீங்கள் எந்தப் பிரிவைச் சேர்ந்தவர்?",
    },
    "ask_gender": {
        "en": "Some schemes give women a lower rate. Who is applying?",
        "hi": "कुछ योजनाओं में महिलाओं को ब्याज में छूट मिलती है। आवेदन कौन कर रहा है?",
        "mr": "काही योजनांमध्ये महिलांना व्याजात सवलत मिळते. अर्ज कोण करत आहे?",
        "bn": "কিছু প্রকল্পে মহিলাদের সুদের হার কম। আবেদন করছেন কে?",
        "ta": "சில திட்டங்களில் பெண்களுக்கு வட்டி குறைவு. யார் விண்ணப்பிக்கிறார்?",
    },
    "opt_woman": {"en": "A woman", "hi": "महिला", "mr": "महिला", "bn": "একজন মহিলা", "ta": "ஒரு பெண்"},
    "opt_man": {"en": "A man", "hi": "पुरुष", "mr": "पुरुष", "bn": "একজন পুরুষ", "ta": "ஒரு ஆண்"},
    "opt_other": {"en": "Other", "hi": "अन्य", "mr": "इतर", "bn": "অন্যান্য", "ta": "மற்றவை"},
    "ask_place": {
        "en": "Last one — where are you? I'll find offices near you.",
        "hi": "आख़िरी सवाल — आप कहाँ रहते हैं? मैं आपके पास के कार्यालय ढूँढ़ूँगा।",
        "mr": "शेवटचा प्रश्न — तुम्ही कुठे राहता? मी जवळची कार्यालये शोधतो.",
        "bn": "শেষ প্রশ্ন — আপনি কোথায় থাকেন? আমি কাছের দপ্তর খুঁজে দেব।",
        "ta": "கடைசி கேள்வி — நீங்கள் எங்கு இருக்கிறீர்கள்? அருகிலுள்ள அலுவலகங்களைத் தேடுகிறேன்.",
    },

    # ---- the adaptive interview ----
    #
    # Which of these gets asked, and in what order, is decided at runtime by
    # `src.interview` against the schemes still in play — so these are written to
    # stand alone. None may assume a previous question was asked, because for
    # most people it was not.
    "ask_occupation": {
        "en": "What work do you do? It decides more schemes than anything else you can tell me.",
        "hi": "आप क्या काम करते हैं? सबसे ज़्यादा योजनाएँ इसी से तय होती हैं।",
        "mr": "तुम्ही काय काम करता? सर्वात जास्त योजना याच उत्तरावर ठरतात.",
        "bn": "আপনি কী কাজ করেন? সবচেয়ে বেশি প্রকল্প এর উপরেই নির্ভর করে।",
        "ta": "நீங்கள் என்ன வேலை செய்கிறீர்கள்? மிக அதிகத் திட்டங்கள் இதைப் பொறுத்தே முடிவாகும்.",
    },
    "ask_age": {
        "en": "How old are you?",
        "hi": "आपकी उम्र क्या है?",
        "mr": "तुमचे वय किती आहे?",
        "bn": "আপনার বয়স কত?",
        "ta": "உங்கள் வயது என்ன?",
    },
    "ask_gender": {
        "en": "Who is this for?",
        "hi": "यह किसके लिए है?",
        "mr": "हे कोणासाठी आहे?",
        "bn": "এটি কার জন্য?",
        "ta": "இது யாருக்காக?",
    },
    "ask_caste": {
        "en": "Which community do you belong to? Many schemes are reserved, and this is the only way to see them.",
        "hi": "आप किस समुदाय से हैं? कई योजनाएँ आरक्षित हैं, और उन्हें देखने का यही एक रास्ता है।",
        "mr": "तुम्ही कोणत्या समाजाचे आहात? अनेक योजना राखीव आहेत, आणि त्या पाहण्याचा हाच मार्ग आहे.",
        "bn": "আপনি কোন সম্প্রদায়ভুক্ত? অনেক প্রকল্প সংরক্ষিত, আর সেগুলি দেখার এটিই একমাত্র উপায়।",
        "ta": "நீங்கள் எந்தச் சமூகத்தைச் சேர்ந்தவர்? பல திட்டங்கள் ஒதுக்கப்பட்டவை; அவற்றைக் காண இதுவே வழி.",
    },
    "ask_employment": {
        "en": "Are you working at the moment?",
        "hi": "क्या आप अभी काम कर रहे हैं?",
        "mr": "तुम्ही सध्या काम करत आहात का?",
        "bn": "আপনি কি এখন কাজ করছেন?",
        "ta": "நீங்கள் தற்போது வேலை செய்கிறீர்களா?",
    },
    "ask_student": {
        "en": "Are you studying right now?",
        "hi": "क्या आप अभी पढ़ाई कर रहे हैं?",
        "mr": "तुम्ही सध्या शिकत आहात का?",
        "bn": "আপনি কি এখন পড়াশোনা করছেন?",
        "ta": "நீங்கள் இப்போது படிக்கிறீர்களா?",
    },
    "ask_disability": {
        "en": "Do you have a disability certificate?",
        "hi": "क्या आपके पास दिव्यांगता प्रमाणपत्र है?",
        "mr": "तुमच्याकडे दिव्यांग प्रमाणपत्र आहे का?",
        "bn": "আপনার কি প্রতিবন্ধী শংসাপত্র আছে?",
        "ta": "உங்களிடம் மாற்றுத்திறனாளி சான்றிதழ் உள்ளதா?",
    },
    "ask_marital": {
        "en": "Are you married?",
        "hi": "क्या आप विवाहित हैं?",
        "mr": "तुम्ही विवाहित आहात का?",
        "bn": "আপনি কি বিবাহিত?",
        "ta": "நீங்கள் திருமணமானவரா?",
    },
    "ask_residence": {
        "en": "Do you live in a village, or a town or city?",
        "hi": "आप गाँव में रहते हैं या शहर में?",
        "mr": "तुम्ही गावात राहता की शहरात?",
        "bn": "আপনি গ্রামে থাকেন না শহরে?",
        "ta": "நீங்கள் கிராமத்தில் வசிக்கிறீர்களா, நகரத்திலா?",
    },
    "ask_bpl": {
        "en": "Do you have a BPL ration card?",
        "hi": "क्या आपके पास बीपीएल राशन कार्ड है?",
        "mr": "तुमच्याकडे बीपीएल रेशन कार्ड आहे का?",
        "bn": "আপনার কি বিপিএল রেশন কার্ড আছে?",
        "ta": "உங்களிடம் BPL ரேஷன் அட்டை உள்ளதா?",
    },
    "ask_minority": {
        "en": "Do you belong to a minority community?",
        "hi": "क्या आप अल्पसंख्यक समुदाय से हैं?",
        "mr": "तुम्ही अल्पसंख्याक समाजाचे आहात का?",
        "bn": "আপনি কি সংখ্যালঘু সম্প্রদায়ভুক্ত?",
        "ta": "நீங்கள் சிறுபான்மைச் சமூகத்தைச் சேர்ந்தவரா?",
    },
    "ask_income": {
        "en": "Roughly what does your whole household earn in a year? An estimate is fine.",
        "hi": "आपके पूरे परिवार की साल भर की आमदनी लगभग कितनी है? अंदाज़ा ही काफ़ी है।",
        "mr": "तुमच्या संपूर्ण कुटुंबाचे वर्षाचे उत्पन्न साधारण किती? अंदाज पुरेसा आहे.",
        "bn": "আপনার গোটা পরিবারের বছরে আয় আনুমানিক কত? আন্দাজই যথেষ্ট।",
        "ta": "உங்கள் குடும்பத்தின் ஆண்டு வருமானம் தோராயமாக எவ்வளவு? மதிப்பீடே போதும்.",
    },

    "ask_land": {
        "en": "How much farmland do you own? A rough figure is fine, and owning none is an answer that opens schemes of its own.",
        "hi": "आपके पास कितनी खेती की ज़मीन है? अंदाज़ा ही काफ़ी है — और ज़मीन न होना भी एक जवाब है, जिससे अपनी अलग योजनाएँ खुलती हैं।",
        "mr": "तुमच्याकडे किती शेतजमीन आहे? अंदाज पुरेसा आहे — आणि जमीन नसणे हेही एक उत्तर आहे, ज्याने वेगळ्या योजना उघडतात.",
        "bn": "আপনার কত চাষের জমি আছে? আন্দাজই যথেষ্ট — আর জমি না থাকাও একটা উত্তর, তাতে আলাদা প্রকল্প খোলে।",
        "ta": "உங்களிடம் எவ்வளவு விவசாய நிலம் உள்ளது? தோராயமே போதும் — நிலம் இல்லாததும் ஒரு பதில், அதற்கெனத் தனித் திட்டங்கள் உண்டு.",
    },
    "opt_land_0": {
        "en": "None — I don't own land", "hi": "कोई नहीं — मेरे पास ज़मीन नहीं है",
        "mr": "काहीही नाही — माझ्याकडे जमीन नाही", "bn": "নেই — আমার জমি নেই",
        "ta": "இல்லை — எனக்கு நிலம் இல்லை",
    },

    # Offered on every adaptive question. Declining costs precision and never a
    # scheme, and the label has to say so or nobody dares skip the awkward ones.
    "opt_skip": {
        "en": "Skip — it won't hide anything",
        "hi": "छोड़ दें — इससे कुछ छिपेगा नहीं",
        "mr": "वगळा — यामुळे काहीही लपणार नाही",
        "bn": "বাদ দিন — কিছুই লুকোবে না",
        "ta": "தவிர் — இதனால் எதுவும் மறைக்கப்படாது",
    },
    "opt_yes": {"en": "Yes", "hi": "हाँ", "mr": "होय", "bn": "হ্যাঁ", "ta": "ஆம்"},
    "opt_no": {"en": "No", "hi": "नहीं", "mr": "नाही", "bn": "না", "ta": "இல்லை"},
    "opt_rural": {"en": "A village", "hi": "गाँव", "mr": "गाव", "bn": "গ্রাম", "ta": "கிராமம்"},
    "opt_urban": {"en": "A town or city", "hi": "शहर", "mr": "शहर", "bn": "শহর", "ta": "நகரம்"},

    # ---- results ----
    "checking": {
        "en": "Checking every scheme against what you told me…",
        "hi": "आपकी जानकारी हर योजना से मिलाकर देख रहा हूँ…",
        "mr": "तुमची माहिती प्रत्येक योजनेशी तपासत आहे…",
        "bn": "আপনার তথ্য প্রতিটি প্রকল্পের সাথে মিলিয়ে দেখছি…",
        "ta": "உங்கள் தகவலை ஒவ்வொரு திட்டத்துடனும் சரிபார்க்கிறேன்…",
    },
    "result_intro_one": {
        "en": "Good news — you qualify for one scheme.",
        "hi": "अच्छी ख़बर — आप एक योजना के लिए पात्र हैं।",
        "mr": "चांगली बातमी — तुम्ही एका योजनेसाठी पात्र आहात.",
        "bn": "সুখবর — আপনি একটি প্রকল্পের জন্য যোগ্য।",
        "ta": "நல்ல செய்தி — நீங்கள் ஒரு திட்டத்திற்குத் தகுதியானவர்.",
    },
    "result_intro_many": {
        "en": "Good news — you qualify for {n} schemes. They do not cost the same, so I have put the cheapest first.",
        "hi": "अच्छी ख़बर — आप {n} योजनाओं के लिए पात्र हैं। इनकी लागत अलग-अलग है, इसलिए सबसे सस्ती सबसे ऊपर रखी है।",
        "mr": "चांगली बातमी — तुम्ही {n} योजनांसाठी पात्र आहात. त्यांचा खर्च वेगवेगळा आहे, म्हणून सर्वात स्वस्त सर्वात वर ठेवली आहे.",
        "bn": "সুখবর — আপনি {n}টি প্রকল্পের জন্য যোগ্য। এগুলির খরচ এক নয়, তাই সবচেয়ে সস্তাটি উপরে রেখেছি।",
        "ta": "நல்ல செய்தி — நீங்கள் {n} திட்டங்களுக்குத் தகுதியானவர். அவற்றின் செலவு வெவ்வேறு, எனவே மலிவானதை முதலில் வைத்துள்ளேன்.",
    },
    "no_match": {
        "en": "I could not find an NSFDC scheme that fits this exactly.",
        "hi": "मुझे ऐसी कोई NSFDC योजना नहीं मिली जो इसमें बिलकुल सही बैठे।",
        "mr": "यात अगदी बसणारी NSFDC योजना मला सापडली नाही.",
        "bn": "ঠিক এর সাথে মেলে এমন কোনও NSFDC প্রকল্প পাইনি।",
        "ta": "இதற்குச் சரியாகப் பொருந்தும் NSFDC திட்டம் எதுவும் கிடைக்கவில்லை.",
    },

    # ---- card headings ----
    "card_cost": {
        "en": "What this loan really costs", "hi": "इस ऋण की असली लागत",
        "mr": "या कर्जाचा खरा खर्च", "bn": "এই ঋণের প্রকৃত খরচ", "ta": "இந்தக் கடனின் உண்மையான செலவு",
    },
    "card_compare": {
        "en": "Compared to a local moneylender", "hi": "साहूकार से तुलना",
        "mr": "सावकाराशी तुलना", "bn": "স্থানীয় মহাজনের সাথে তুলনা", "ta": "உள்ளூர் வட்டிக்காரருடன் ஒப்பீடு",
    },
    "card_where": {
        "en": "Where to go", "hi": "कहाँ जाएँ", "mr": "कुठे जायचे",
        "bn": "কোথায় যাবেন", "ta": "எங்கு செல்ல வேண்டும்",
    },
    "card_whynot": {
        "en": "Not a match, and why", "hi": "जो योजनाएँ नहीं मिलीं, और क्यों",
        "mr": "न मिळालेल्या योजना, आणि का", "bn": "যেগুলি মেলেনি, এবং কেন",
        "ta": "பொருந்தாதவை, ஏன்",
    },
    "card_blocked": {
        "en": "Cannot help you right now", "hi": "अभी मदद नहीं कर सकते",
        "mr": "आत्ता मदत करू शकत नाहीत", "bn": "এখন সাহায্য করতে পারবে না",
        "ta": "இப்போது உதவ முடியாது",
    },

    # ---- labels ----
    "you_borrow": {"en": "You borrow", "hi": "आप लेंगे", "mr": "तुम्ही घ्याल", "bn": "আপনি নেবেন", "ta": "நீங்கள் பெறுவீர்கள்"},
    "you_repay": {"en": "You repay", "hi": "आप लौटाएँगे", "mr": "तुम्ही परत कराल", "bn": "আপনি ফেরত দেবেন", "ta": "நீங்கள் திருப்பிச் செலுத்துவீர்கள்"},
    "it_costs": {"en": "So it costs you", "hi": "यानी लागत", "mr": "म्हणजे खर्च", "bn": "অর্থাৎ খরচ", "ta": "அதாவது செலவு"},
    "this_scheme": {"en": "This scheme", "hi": "यह योजना", "mr": "ही योजना", "bn": "এই প্রকল্প", "ta": "இந்தத் திட்டம்"},
    "moneylender": {"en": "A moneylender at 5% a month", "hi": "साहूकार, 5% महीना", "mr": "सावकार, दरमहा 5%", "bn": "মহাজন, মাসে 5%", "ta": "வட்டிக்காரர், மாதம் 5%"},
    "you_save": {"en": "You save", "hi": "आपकी बचत", "mr": "तुमची बचत", "bn": "আপনার সাশ্রয়", "ta": "உங்கள் சேமிப்பு"},
    "per_year": {"en": "a year", "hi": "सालाना", "mr": "वार्षिक", "bn": "বছরে", "ta": "ஆண்டுக்கு"},
    "quarterly": {"en": "every 3 months", "hi": "हर 3 महीने", "mr": "दर 3 महिन्यांनी", "bn": "প্রতি ৩ মাসে", "ta": "ஒவ்வொரு 3 மாதமும்"},
    "per_month_budget": {"en": "set aside about {amount} a month", "hi": "हर महीने लगभग {amount} अलग रखें", "mr": "दरमहा सुमारे {amount} बाजूला ठेवा", "bn": "প্রতি মাসে প্রায় {amount} সরিয়ে রাখুন", "ta": "மாதம் சுமார் {amount} ஒதுக்கி வையுங்கள்"},
    "km_away": {"en": "km away", "hi": "किमी दूर", "mr": "किमी अंतरावर", "bn": "কিমি দূরে", "ta": "கிமீ தொலைவில்"},
    "cheapest": {"en": "Lowest cost", "hi": "सबसे सस्ती", "mr": "सर्वात स्वस्त", "bn": "সবচেয়ে সস্তা", "ta": "மிகக் குறைந்த செலவு"},

    # ---- trust ----
    # Widened from "NSFDC never charges" once this stopped being a credit tool.
    # The claim is still exactly true of every scheme in the corpus, and the fee
    # charged for knowing which scheme exists is the thing this product is
    # against — so the warning belongs on a pension and a scholarship too, not
    # only on a loan.
    "fraud_shield": {
        "en": "No government scheme charges a fee to apply. If anyone asks you for money to process or approve your application, that is fraud.",
        "hi": "किसी भी सरकारी योजना में आवेदन का कोई शुल्क नहीं होता। अगर कोई आपसे आवेदन पास कराने के नाम पर पैसे माँगे, तो वह धोखाधड़ी है।",
        "mr": "कोणतीही सरकारी योजना अर्जासाठी शुल्क घेत नाही. अर्ज मंजूर करण्यासाठी कोणी पैसे मागत असेल, तर ती फसवणूक आहे.",
        "bn": "কোনও সরকারি প্রকল্পে আবেদনের ফি লাগে না। আবেদন পাশ করানোর নামে কেউ টাকা চাইলে সেটি প্রতারণা।",
        "ta": "எந்த அரசுத் திட்டமும் விண்ணப்பிக்கக் கட்டணம் வசூலிப்பதில்லை. விண்ணப்பத்தை அனுமதிக்க யாரேனும் பணம் கேட்டால், அது மோசடி.",
    },
    "estimates_note": {
        "en": "These are estimates. Final terms are set by the office you apply to.",
        "hi": "ये अनुमान हैं। अंतिम शर्तें उस कार्यालय द्वारा तय होंगी जहाँ आप आवेदन करेंगे।",
        "mr": "हे अंदाज आहेत. अंतिम अटी तुम्ही अर्ज कराल त्या कार्यालयाकडून ठरतील.",
        "bn": "এগুলি আনুমানিক। চূড়ান্ত শর্ত ঠিক করবে যে দপ্তরে আপনি আবেদন করবেন।",
        "ta": "இவை மதிப்பீடுகள். இறுதி நிபந்தனைகளை நீங்கள் விண்ணப்பிக்கும் அலுவலகம் நிர்ணயிக்கும்.",
    },

    # ---- UI chrome ----
    "app_tagline": {
        "en": "Government loans, explained plainly", "hi": "सरकारी ऋण, आसान भाषा में",
        "mr": "सरकारी कर्ज, सोप्या भाषेत", "bn": "সরকারি ঋণ, সহজ ভাষায়", "ta": "அரசு கடன்கள், எளிய மொழியில்",
    },
    "start_now": {"en": "Start", "hi": "शुरू करें", "mr": "सुरू करा", "bn": "শুরু করুন", "ta": "தொடங்கு"},
    "type_here": {"en": "Type your answer, or tap an option", "hi": "अपना जवाब लिखें, या विकल्प चुनें", "mr": "तुमचे उत्तर लिहा, किंवा पर्याय निवडा", "bn": "উত্তর লিখুন, বা বিকল্প বেছে নিন", "ta": "பதிலை எழுதுங்கள், அல்லது ஒன்றைத் தேர்வு செய்யுங்கள்"},
    "start_over": {"en": "Start over", "hi": "फिर से शुरू करें", "mr": "पुन्हा सुरू करा", "bn": "আবার শুরু করুন", "ta": "மீண்டும் தொடங்கு"},
    "didnt_understand": {
        "en": "Sorry, I did not follow that. Could you say it another way, or tap one of the options?",
        "hi": "माफ़ कीजिए, मैं समझ नहीं पाया। दूसरे शब्दों में बताएँ, या नीचे से कोई विकल्प चुनें।",
        "mr": "क्षमस्व, मला समजले नाही. दुसऱ्या शब्दांत सांगा, किंवा खालील पर्याय निवडा.",
        "bn": "দুঃখিত, বুঝতে পারিনি। অন্যভাবে বলুন, বা নিচের একটি বিকল্প বেছে নিন।",
        "ta": "மன்னிக்கவும், புரியவில்லை. வேறு விதமாகச் சொல்லுங்கள், அல்லது கீழே ஒன்றைத் தேர்வு செய்யுங்கள்.",
    },
}


def t(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """Look up a string, falling back to English then to the key itself.

    Falling back to English rather than raising matters: a missing translation
    should degrade to a comprehensible message, never to a blank screen or a
    stack trace, in front of someone trying to get a loan.
    """
    entry = STRINGS.get(key, {})
    text = entry.get(lang) or entry.get(DEFAULT_LANGUAGE) or key
    return text.format(**kwargs) if kwargs else text


def ui_strings(lang: str = DEFAULT_LANGUAGE) -> dict[str, str]:
    """The whole catalogue in one language, for the browser to hold."""
    return {key: t(key, lang) for key in STRINGS}
