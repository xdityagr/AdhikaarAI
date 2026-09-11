"""
Opt-out, and the notice that comes before anything else.

This lived inside the old LangGraph flow and was very nearly lost when WhatsApp
moved to the shared brain — which would have been the worst kind of regression,
because STOP is not a feature. On a channel that reaches someone's personal
phone, the ability to make it stop is the difference between a service and a
nuisance, and honouring it is required by both WhatsApp's policy and Twilio's.

What changed deliberately: START is no longer a gate. Joining the Twilio
sandbox is itself an opt-in, and demanding a second magic word before answering
a question turns a person away at the door for a formality. So the first
message gets the notice *and* an answer. STOP still stops everything, at any
point, in any of the supported languages.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Opted-out numbers. In memory, which is honest for a demo and wrong for
# production: a restart forgets that someone asked to be left alone, and that
# is the one thing this file exists to remember. Moving it into the database is
# the first thing to do before this handles real traffic.
_OPTED_OUT: set[str] = set()

# Written in each script rather than transliterated, because someone who wants
# this to stop should not have to type in English to make it happen.
STOP_WORDS = {
    "stop", "unsubscribe", "cancel", "end", "quit",
    "बंद", "रोको", "बंद करो",                     # Hindi
    "থামো", "বন্ধ",                                # Bengali
    "थांबा",                                       # Marathi
    "ఆపు", "ఆపండి",                                # Telugu
    "நிறுத்து",                                    # Tamil
    "બંધ",                                         # Gujarati
    "ನಿಲ್ಲಿಸಿ",                                     # Kannada
    "നിർത്തുക",                                    # Malayalam
    "ਬੰਦ",                                         # Punjabi
    "ବନ୍ଦ",                                        # Odia
    "বন্ধ কৰক",                                    # Assamese
    "بند",                                         # Urdu
}

START_WORDS = {"start", "शुरू", "शुरु", "চালু", "தொடங்கு", "प्रारंभ", "resume"}

# One line, in the person's own language, sent once as a footer under the first
# real answer.
#
# It used to be three English paragraphs sitting ABOVE the answer, and it cost
# more than it looks: WhatsApp folds a long message behind "Read more", so the
# notice pushed the actual answer out of sight, and it arrived in English next
# to a Hindi reply. A privacy notice nobody reads protects nobody. What has to
# survive is the substance — the data is only used for matching, we never ask
# for Aadhaar or money, and STOP works — so that is all that is left.
NOTICES = {
    "en": "🔒 _Your answers are only used to find schemes. I never ask for your "
          "Aadhaar number, bank password or any fee. Send *STOP* to end._",
    "hi": "🔒 _आपकी जानकारी सिर्फ़ योजनाएँ ढूँढने के लिए है। मैं कभी आधार नंबर, बैंक "
          "पासवर्ड या पैसा नहीं माँगती। बंद करने के लिए *STOP* भेजें।_",
    "mr": "🔒 _तुमची माहिती फक्त योजना शोधण्यासाठी वापरली जाते. मी कधीही आधार क्रमांक, "
          "बँक पासवर्ड किंवा पैसे मागत नाही. थांबवण्यासाठी *STOP* पाठवा._",
    "bn": "🔒 _আপনার তথ্য শুধু প্রকল্প খুঁজতে ব্যবহার হয়। আমি কখনও আধার নম্বর, ব্যাঙ্কের "
          "পাসওয়ার্ড বা টাকা চাই না। বন্ধ করতে *STOP* পাঠান।_",
    "ta": "🔒 _உங்கள் தகவல் திட்டங்களைத் தேட மட்டுமே பயன்படுகிறது. ஆதார் எண், வங்கி "
          "கடவுச்சொல் அல்லது பணம் நான் ஒருபோதும் கேட்பதில்லை. நிறுத்த *STOP* அனுப்பவும்._",
    "te": "🔒 _మీ సమాచారం పథకాలు వెతకడానికి మాత్రమే. ఆధార్ నంబర్, బ్యాంక్ పాస్‌వర్డ్ లేదా "
          "డబ్బు నేను ఎప్పుడూ అడగను. ఆపడానికి *STOP* పంపండి._",
    "gu": "🔒 _તમારી માહિતી ફક્ત યોજનાઓ શોધવા વપરાય છે. હું ક્યારેય આધાર નંબર, બેંક "
          "પાસવર્ડ કે પૈસા માંગતી નથી. બંધ કરવા *STOP* મોકલો._",
    "kn": "🔒 _ನಿಮ್ಮ ಮಾಹಿತಿ ಯೋಜನೆಗಳನ್ನು ಹುಡುಕಲು ಮಾತ್ರ. ಆಧಾರ್ ಸಂಖ್ಯೆ, ಬ್ಯಾಂಕ್ ಪಾಸ್‌ವರ್ಡ್ "
          "ಅಥವಾ ಹಣ ನಾನು ಎಂದಿಗೂ ಕೇಳುವುದಿಲ್ಲ. ನಿಲ್ಲಿಸಲು *STOP* ಕಳುಹಿಸಿ._",
    "ml": "🔒 _നിങ്ങളുടെ വിവരങ്ങൾ പദ്ധതികൾ കണ്ടെത്താൻ മാത്രം. ആധാർ നമ്പർ, ബാങ്ക് "
          "പാസ്‌വേഡ് അല്ലെങ്കിൽ പണം ഞാൻ ഒരിക്കലും ചോദിക്കില്ല. നിർത്താൻ *STOP* അയക്കുക._",
    "pa": "🔒 _ਤੁਹਾਡੀ ਜਾਣਕਾਰੀ ਸਿਰਫ਼ ਸਕੀਮਾਂ ਲੱਭਣ ਲਈ ਹੈ। ਮੈਂ ਕਦੇ ਆਧਾਰ ਨੰਬਰ, ਬੈਂਕ ਪਾਸਵਰਡ ਜਾਂ "
          "ਪੈਸੇ ਨਹੀਂ ਮੰਗਦੀ। ਬੰਦ ਕਰਨ ਲਈ *STOP* ਭੇਜੋ।_",
    "or": "🔒 _ଆପଣଙ୍କ ସୂଚନା କେବଳ ଯୋଜନା ଖୋଜିବା ପାଇଁ। ମୁଁ କେବେ ଆଧାର ନମ୍ବର, ବ୍ୟାଙ୍କ ପାସୱାର୍ଡ "
          "କିମ୍ବା ଟଙ୍କା ମାଗେ ନାହିଁ। ବନ୍ଦ କରିବାକୁ *STOP* ପଠାନ୍ତୁ।_",
    "as": "🔒 _আপোনাৰ তথ্য কেৱল আঁচনি বিচাৰিবলৈহে ব্যৱহাৰ হয়। মই কেতিয়াও আধাৰ নম্বৰ, "
          "বেংকৰ পাছৱৰ্ড বা টকা নিবিচাৰোঁ। বন্ধ কৰিবলৈ *STOP* পঠিয়াওক।_",
    "ur": "🔒 _آپ کی معلومات صرف اسکیمیں تلاش کرنے کے لیے ہیں۔ میں کبھی آدھار نمبر، "
          "بینک پاس ورڈ یا پیسے نہیں مانگتی۔ بند کرنے کے لیے *STOP* بھیجیں۔_",
}

NOTICE = NOTICES["en"]


def notice(language: str | None) -> str:
    """The privacy line in the language this person is writing in."""
    return NOTICES.get(language or "en", NOTICES["en"])

STOPPED = (
    "Stopped. I will not message you again.\n\n"
    "Your answers have been cleared. Reply *START* whenever you want to begin "
    "again — there is no charge and no penalty for stopping."
)

RESUMED = "Welcome back. What do you need help with?"


def _normalise(text: str) -> str:
    return text.strip().strip(".!।").casefold()


def is_stop(text: str) -> bool:
    return _normalise(text) in {word.casefold() for word in STOP_WORDS}


def is_start(text: str) -> bool:
    return _normalise(text) in {word.casefold() for word in START_WORDS}


def has_opted_out(user_id: str) -> bool:
    return user_id in _OPTED_OUT


def opt_out(user_id: str) -> None:
    _OPTED_OUT.add(user_id)
    logger.info("Opted out: %s", user_id[:10] + "…")


def opt_in(user_id: str) -> None:
    _OPTED_OUT.discard(user_id)


def check(user_id: str, text: str) -> str | None:
    """The reply consent requires, or None to let the message through.

    Order matters: STOP is honoured before anything else, including before an
    opted-out check, so that sending it twice is harmless rather than ignored.
    """
    if is_stop(text):
        opt_out(user_id)
        return STOPPED

    if has_opted_out(user_id):
        if is_start(text):
            opt_in(user_id)
            return RESUMED
        # Silence, deliberately. Someone who asked not to be messaged should
        # not get a reply explaining that they will not get replies.
        return ""

    return None
