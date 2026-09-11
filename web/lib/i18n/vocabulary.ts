/**
 * myScheme's controlled vocabulary, in the reader's language.
 *
 * These are not interface strings, they are DATA — the exact category and
 * level names the corpus is indexed by. So the English string stays the value
 * used for filtering and only the label is translated; translate the value and
 * `?category=…` matches nothing, silently, which is the same failure mode as
 * getting a facet string wrong against the API.
 *
 * They live here rather than in `locales/` for that reason: a missing entry
 * must fall back to the English name, which is a real category a person can
 * still act on, not a raw key.
 */

import type { Lang } from "@/lib/i18n/config";

type Vocabulary = Record<string, Partial<Record<Lang, string>>>;

export const CATEGORY_LABELS: Vocabulary = {
  "Social welfare & Empowerment": {
    hi: "समाज कल्याण और सशक्तिकरण",
    mr: "समाजकल्याण आणि सक्षमीकरण",
    bn: "সমাজকল্যাণ ও ক্ষমতায়ন",
    ta: "சமூக நலன் மற்றும் அதிகாரமளித்தல்",
    te: "సమాజ సంక్షేమం మరియు సాధికారత",
    gu: "સમાજ કલ્યાણ અને સશક્તિકરણ",
    kn: "ಸಮಾಜ ಕಲ್ಯಾಣ ಮತ್ತು ಸಬಲೀಕರಣ",
    ml: "സാമൂഹ്യക്ഷേമവും ശാക്തീകരണവും",
    pa: "ਸਮਾਜ ਭਲਾਈ ਅਤੇ ਸਸ਼ਕਤੀਕਰਨ",
    or: "ସମାଜ କଲ୍ୟାଣ ଓ ସଶକ୍ତିକରଣ",
    as: "সমাজ কল্যাণ আৰু সশক্তিকৰণ",
    ur: "سماجی بہبود اور بااختیار بنانا",
  },
  "Education & Learning": {
    hi: "शिक्षा और सीखना",
    mr: "शिक्षण आणि अध्ययन",
    bn: "শিক্ষা ও শেখা",
    ta: "கல்வி மற்றும் கற்றல்",
    te: "విద్య మరియు అభ్యాసం",
    gu: "શિક્ષણ અને શીખવું",
    kn: "ಶಿಕ್ಷಣ ಮತ್ತು ಕಲಿಕೆ",
    ml: "വിദ്യാഭ്യാസവും പഠനവും",
    pa: "ਸਿੱਖਿਆ ਅਤੇ ਸਿੱਖਣਾ",
    or: "ଶିକ୍ଷା ଓ ଶିକ୍ଷଣ",
    as: "শিক্ষা আৰু শিকা",
    ur: "تعلیم اور سیکھنا",
  },
  "Agriculture,Rural & Environment": {
    hi: "कृषि, ग्रामीण और पर्यावरण",
    mr: "शेती, ग्रामीण आणि पर्यावरण",
    bn: "কৃষি, গ্রামীণ ও পরিবেশ",
    ta: "வேளாண்மை, கிராமப்புறம் மற்றும் சுற்றுச்சூழல்",
    te: "వ్యవసాయం, గ్రామీణం మరియు పర్యావరణం",
    gu: "ખેતી, ગ્રામીણ અને પર્યાવરણ",
    kn: "ಕೃಷಿ, ಗ್ರಾಮೀಣ ಮತ್ತು ಪರಿಸರ",
    ml: "കൃഷി, ഗ്രാമീണം, പരിസ്ഥിതി",
    pa: "ਖੇਤੀਬਾੜੀ, ਪੇਂਡੂ ਅਤੇ ਵਾਤਾਵਰਣ",
    or: "କୃଷି, ଗ୍ରାମୀଣ ଓ ପରିବେଶ",
    as: "কৃষি, গ্ৰামীণ আৰু পৰিৱেশ",
    ur: "زراعت، دیہی اور ماحولیات",
  },
  "Business & Entrepreneurship": {
    hi: "व्यापार और उद्यमिता",
    mr: "व्यवसाय आणि उद्योजकता",
    bn: "ব্যবসা ও উদ্যোগ",
    ta: "வணிகம் மற்றும் தொழில்முனைவு",
    te: "వ్యాపారం మరియు వ్యవస్థాపకత",
    gu: "વ્યવસાય અને ઉદ્યોગસાહસિકતા",
    kn: "ವ್ಯಾಪಾರ ಮತ್ತು ಉದ್ಯಮಶೀಲತೆ",
    ml: "വ്യാപാരവും സംരംഭകത്വവും",
    pa: "ਕਾਰੋਬਾਰ ਅਤੇ ਉੱਦਮਤਾ",
    or: "ବ୍ୟବସାୟ ଓ ଉଦ୍ୟୋଗିତା",
    as: "ব্যৱসায় আৰু উদ্যোগিতা",
    ur: "کاروبار اور کاروباری اقدام",
  },
  "Women and Child": {
    hi: "महिला और बच्चे",
    mr: "महिला आणि बालक",
    bn: "নারী ও শিশু",
    ta: "பெண்கள் மற்றும் குழந்தைகள்",
    te: "మహిళలు మరియు పిల్లలు",
    gu: "મહિલા અને બાળક",
    kn: "ಮಹಿಳೆ ಮತ್ತು ಮಕ್ಕಳು",
    ml: "സ്ത്രീകളും കുട്ടികളും",
    pa: "ਔਰਤਾਂ ਅਤੇ ਬੱਚੇ",
    or: "ମହିଳା ଓ ଶିଶୁ",
    as: "মহিলা আৰু শিশু",
    ur: "خواتین اور بچے",
  },
  "Skills & Employment": {
    hi: "कौशल और रोज़गार",
    mr: "कौशल्य आणि रोजगार",
    bn: "দক্ষতা ও কর্মসংস্থান",
    ta: "திறன் மற்றும் வேலைவாய்ப்பு",
    te: "నైపుణ్యాలు మరియు ఉపాధి",
    gu: "કૌશલ્ય અને રોજગાર",
    kn: "ಕೌಶಲ್ಯ ಮತ್ತು ಉದ್ಯೋಗ",
    ml: "നൈപുണ്യവും തൊഴിലും",
    pa: "ਹੁਨਰ ਅਤੇ ਰੁਜ਼ਗਾਰ",
    or: "କୌଶଳ ଓ ନିଯୁକ୍ତି",
    as: "দক্ষতা আৰু নিয়োগ",
    ur: "ہنر اور روزگار",
  },
  "Banking,Financial Services and Insurance": {
    hi: "बैंकिंग, वित्तीय सेवाएँ और बीमा",
    mr: "बँकिंग, वित्तीय सेवा आणि विमा",
    bn: "ব্যাঙ্কিং, আর্থিক পরিষেবা ও বিমা",
    ta: "வங்கி, நிதிச் சேவைகள் மற்றும் காப்பீடு",
    te: "బ్యాంకింగ్, ఆర్థిక సేవలు మరియు బీమా",
    gu: "બેંકિંગ, નાણાકીય સેવાઓ અને વીમો",
    kn: "ಬ್ಯಾಂಕಿಂಗ್, ಹಣಕಾಸು ಸೇವೆಗಳು ಮತ್ತು ವಿಮೆ",
    ml: "ബാങ്കിംഗ്, ധനകാര്യ സേവനങ്ങൾ, ഇൻഷുറൻസ്",
    pa: "ਬੈਂਕਿੰਗ, ਵਿੱਤੀ ਸੇਵਾਵਾਂ ਅਤੇ ਬੀਮਾ",
    or: "ବ୍ୟାଙ୍କିଂ, ଆର୍ଥିକ ସେବା ଓ ବୀମା",
    as: "বেংকিং, বিত্তীয় সেৱা আৰু বীমা",
    ur: "بینکاری، مالی خدمات اور بیمہ",
  },
  "Health & Wellness": {
    hi: "स्वास्थ्य और तंदुरुस्ती",
    mr: "आरोग्य आणि स्वास्थ्य",
    bn: "স্বাস্থ্য ও সুস্থতা",
    ta: "உடல்நலம் மற்றும் நல்வாழ்வு",
    te: "ఆరోగ్యం మరియు క్షేమం",
    gu: "આરોગ્ય અને સુખાકારી",
    kn: "ಆರೋಗ್ಯ ಮತ್ತು ಸ್ವಾಸ್ಥ್ಯ",
    ml: "ആരോഗ്യവും ക്ഷേമവും",
    pa: "ਸਿਹਤ ਅਤੇ ਤੰਦਰੁਸਤੀ",
    or: "ସ୍ୱାସ୍ଥ୍ୟ ଓ ସୁସ୍ଥତା",
    as: "স্বাস্থ্য আৰু সুস্থতা",
    ur: "صحت اور تندرستی",
  },
  "Sports & Culture": {
    hi: "खेल और संस्कृति",
    mr: "क्रीडा आणि संस्कृती",
    bn: "খেলাধুলা ও সংস্কৃতি",
    ta: "விளையாட்டு மற்றும் பண்பாடு",
    te: "క్రీడలు మరియు సంస్కృతి",
    gu: "રમતગમત અને સંસ્કૃતિ",
    kn: "ಕ್ರೀಡೆ ಮತ್ತು ಸಂಸ್ಕೃತಿ",
    ml: "കായികവും സംസ്കാരവും",
    pa: "ਖੇਡਾਂ ਅਤੇ ਸੱਭਿਆਚਾਰ",
    or: "କ୍ରୀଡ଼ା ଓ ସଂସ୍କୃତି",
    as: "ক্ৰীড়া আৰু সংস্কৃতি",
    ur: "کھیل اور ثقافت",
  },
  "Housing & Shelter": {
    hi: "आवास और आश्रय",
    mr: "घर आणि निवारा",
    bn: "বাসস্থান ও আশ্রয়",
    ta: "வீடு மற்றும் தங்குமிடம்",
    te: "గృహం మరియు ఆశ్రయం",
    gu: "આવાસ અને આશ્રય",
    kn: "ವಸತಿ ಮತ್ತು ಆಶ್ರಯ",
    ml: "പാർപ്പിടവും അഭയവും",
    pa: "ਰਿਹਾਇਸ਼ ਅਤੇ ਆਸਰਾ",
    or: "ଆବାସ ଓ ଆଶ୍ରୟ",
    as: "বাসগৃহ আৰু আশ্ৰয়",
    ur: "رہائش اور پناہ",
  },
  "Science, IT & Communications": {
    hi: "विज्ञान, आईटी और संचार",
    mr: "विज्ञान, आयटी आणि दळणवळण",
    bn: "বিজ্ঞান, আইটি ও যোগাযোগ",
    ta: "அறிவியல், தகவல் தொழில்நுட்பம் மற்றும் தொடர்பு",
    te: "విజ్ఞానం, ఐటీ మరియు సమాచార రంగం",
    gu: "વિજ્ઞાન, આઈટી અને સંચાર",
    kn: "ವಿಜ್ಞಾನ, ಐಟಿ ಮತ್ತು ಸಂವಹನ",
    ml: "ശാസ്ത്രം, ഐടി, വാർത്താവിനിമയം",
    pa: "ਵਿਗਿਆਨ, ਆਈਟੀ ਅਤੇ ਸੰਚਾਰ",
    or: "ବିଜ୍ଞାନ, ଆଇଟି ଓ ଯୋଗାଯୋଗ",
    as: "বিজ্ঞান, আইটি আৰু যোগাযোগ",
    ur: "سائنس، آئی ٹی اور مواصلات",
  },
  "Transport & Infrastructure": {
    hi: "परिवहन और बुनियादी ढाँचा",
    mr: "वाहतूक आणि पायाभूत सुविधा",
    bn: "পরিবহন ও পরিকাঠামো",
    ta: "போக்குவரத்து மற்றும் உள்கட்டமைப்பு",
    te: "రవాణా మరియు మౌలిక సదుపాయాలు",
    gu: "પરિવહન અને માળખાગત સુવિધા",
    kn: "ಸಾರಿಗೆ ಮತ್ತು ಮೂಲಸೌಕರ್ಯ",
    ml: "ഗതാഗതവും അടിസ്ഥാനസൗകര്യവും",
    pa: "ਆਵਾਜਾਈ ਅਤੇ ਬੁਨਿਆਦੀ ਢਾਂਚਾ",
    or: "ପରିବହନ ଓ ଭିତ୍ତିଭୂମି",
    as: "পৰিবহণ আৰু আন্তঃগাঁথনি",
    ur: "نقل و حمل اور بنیادی ڈھانچہ",
  },
  "Travel & Tourism": {
    hi: "यात्रा और पर्यटन",
    mr: "प्रवास आणि पर्यटन",
    bn: "ভ্রমণ ও পর্যটন",
    ta: "பயணம் மற்றும் சுற்றுலா",
    te: "ప్రయాణం మరియు పర్యాటకం",
    gu: "પ્રવાસ અને પર્યટન",
    kn: "ಪ್ರಯಾಣ ಮತ್ತು ಪ್ರವಾಸೋದ್ಯಮ",
    ml: "യാത്രയും വിനോദസഞ്ചാരവും",
    pa: "ਸਫ਼ਰ ਅਤੇ ਸੈਰ-ਸਪਾਟਾ",
    or: "ଯାତ୍ରା ଓ ପର୍ଯ୍ୟଟନ",
    as: "ভ্ৰমণ আৰু পৰ্যটন",
    ur: "سفر اور سیاحت",
  },
  "Utility & Sanitation": {
    hi: "उपयोगी सेवाएँ और स्वच्छता",
    mr: "उपयोगिता सेवा आणि स्वच्छता",
    bn: "পরিষেবা ও স্যানিটেশন",
    ta: "பயன்பாட்டுச் சேவைகள் மற்றும் துப்புரவு",
    te: "వినియోగ సేవలు మరియు పారిశుద్ధ్యం",
    gu: "ઉપયોગિતા સેવા અને સ્વચ્છતા",
    kn: "ಸೌಕರ್ಯ ಸೇವೆ ಮತ್ತು ನೈರ್ಮಲ್ಯ",
    ml: "അടിസ്ഥാന സേവനങ്ങളും ശുചിത്വവും",
    pa: "ਸਹੂਲਤ ਸੇਵਾਵਾਂ ਅਤੇ ਸਫ਼ਾਈ",
    or: "ଉପଯୋଗିତା ସେବା ଓ ପରିମଳ",
    as: "সেৱা আৰু চাফাই",
    ur: "بنیادی سہولیات اور صفائی",
  },
  "Public Safety,Law & Justice": {
    hi: "जन सुरक्षा, क़ानून और न्याय",
    mr: "सार्वजनिक सुरक्षा, कायदा आणि न्याय",
    bn: "জননিরাপত্তা, আইন ও বিচার",
    ta: "பொதுப் பாதுகாப்பு, சட்டம் மற்றும் நீதி",
    te: "ప్రజా భద్రత, చట్టం మరియు న్యాయం",
    gu: "જાહેર સલામતી, કાયદો અને ન્યાય",
    kn: "ಸಾರ್ವಜನಿಕ ಸುರಕ್ಷತೆ, ಕಾನೂನು ಮತ್ತು ನ್ಯಾಯ",
    ml: "പൊതുസുരക്ഷ, നിയമം, നീതി",
    pa: "ਜਨਤਕ ਸੁਰੱਖਿਆ, ਕਾਨੂੰਨ ਅਤੇ ਨਿਆਂ",
    or: "ଜନ ସୁରକ୍ଷା, ଆଇନ ଓ ନ୍ୟାୟ",
    as: "ৰাজহুৱা সুৰক্ষা, আইন আৰু ন্যায়",
    ur: "عوامی تحفظ، قانون اور انصاف",
  },
};

/** Central vs State — shown on every card and every scheme page. */
export const LEVEL_LABELS: Vocabulary = {
  Central: {
    hi: "केंद्रीय", mr: "केंद्रीय", bn: "কেন্দ্রীয়", ta: "மத்திய",
    te: "కేంద్ర", gu: "કેન્દ્રીય", kn: "ಕೇಂದ್ರ", ml: "കേന്ദ്ര",
    pa: "ਕੇਂਦਰੀ", or: "କେନ୍ଦ୍ରୀୟ", as: "কেন্দ্ৰীয়", ur: "مرکزی",
  },
  State: {
    hi: "राज्य", mr: "राज्य", bn: "রাজ্য", ta: "மாநில",
    te: "రాష్ట్ర", gu: "રાજ્ય", kn: "ರಾಜ್ಯ", ml: "സംസ്ഥാന",
    pa: "ਰਾਜ", or: "ରାଜ୍ୟ", as: "ৰাজ্য", ur: "ریاستی",
  },
};

function label(table: Vocabulary, lang: Lang, name: string): string {
  // English falls through to the name itself, which IS the English label —
  // and so does anything we have not translated yet. A missing entry shows a
  // real category name, never a blank or a key.
  return table[name]?.[lang] ?? name;
}

export const categoryLabel = (lang: Lang, name: string) =>
  label(CATEGORY_LABELS, lang, name);

export const levelLabel = (lang: Lang, name: string) =>
  label(LEVEL_LABELS, lang, name);

/**
 * The reasons a scheme matched, or did not.
 *
 * `/api/discover` returns these in `matched_on`, `unknown` and `unmet`, and
 * they are the engine's own field names — a closed set of sixteen, listed in
 * `_FACET_LABELS`, `_FLAG_FACETS` and the literals beside them in
 * `src/discovery.py`. They were rendered raw, so a Hindi results page said
 * "मेल नहीं खाता gender": the sentence translated and the thing it was about
 * did not.
 *
 * They belong here rather than in `locales/` for the same reason the categories
 * do — they are data the engine emits, and an untranslated one has to fall back
 * to a word a person can still act on rather than to a key.
 */
export const FACET_LABELS: Vocabulary = {
  age: {
    hi: "उम्र", mr: "वय", bn: "বয়স", ta: "வயது", te: "వయసు", gu: "ઉંમર",
    kn: "ವಯಸ್ಸು", ml: "പ്രായം", pa: "ਉਮਰ", or: "ବୟସ", as: "বয়স", ur: "عمر",
  },
  // A scheme that caps what you may own. Added after the coverage test below
  // found it: `_check_assets` emits this and nothing else did, so it was the
  // one facet still reaching every reader in English.
  assets: {
    hi: "संपत्ति", mr: "मालमत्ता", bn: "সম্পত্তি", ta: "சொத்து",
    te: "ఆస్తులు", gu: "મિલકત", kn: "ಆಸ್ತಿ", ml: "ആസ്തി", pa: "ਜਾਇਦਾਦ",
    or: "ସମ୍ପତ୍ତି", as: "সম্পত্তি", ur: "جائیداد",
  },
  caste: {
    hi: "जाति", mr: "जात", bn: "জাতি", ta: "சாதி", te: "కులం", gu: "જાતિ",
    kn: "ಜಾತಿ", ml: "ജാതി", pa: "ਜਾਤ", or: "ଜାତି", as: "জাতি", ur: "ذات",
  },
  gender: {
    hi: "लिंग", mr: "लिंग", bn: "লিঙ্গ", ta: "பாலினம்", te: "లింగం",
    gu: "લિંગ", kn: "ಲಿಂಗ", ml: "ലിംഗം", pa: "ਲਿੰਗ", or: "ଲିଙ୍ଗ",
    as: "লিংগ", ur: "جنس",
  },
  state: {
    hi: "राज्य", mr: "राज्य", bn: "রাজ্য", ta: "மாநிலம்", te: "రాష్ట్రం",
    gu: "રાજ્ય", kn: "ರಾಜ್ಯ", ml: "സംസ്ഥാനം", pa: "ਰਾਜ", or: "ରାଜ୍ୟ",
    as: "ৰাজ্য", ur: "ریاست",
  },
  residence: {
    hi: "निवास", mr: "निवास", bn: "বসবাস", ta: "வசிப்பிடம்", te: "నివాసం",
    gu: "રહેઠાણ", kn: "ವಾಸಸ್ಥಳ", ml: "താമസം", pa: "ਰਿਹਾਇਸ਼", or: "ବସବାସ",
    as: "বসবাস", ur: "رہائش",
  },
  occupation: {
    hi: "काम", mr: "काम", bn: "কাজ", ta: "தொழில்", te: "వృత్తి", gu: "કામ",
    kn: "ಉದ್ಯೋಗ", ml: "തൊഴിൽ", pa: "ਕੰਮ", or: "କାମ", as: "কাম", ur: "کام",
  },
  employment: {
    hi: "रोज़गार", mr: "रोजगार", bn: "কর্মসংস্থান", ta: "வேலைவாய்ப்பு",
    te: "ఉపాధి", gu: "રોજગાર", kn: "ಉದ್ಯೋಗ ಸ್ಥಿತಿ", ml: "തൊഴിൽ നില",
    pa: "ਰੁਜ਼ਗਾਰ", or: "ନିଯୁକ୍ତି", as: "নিয়োগ", ur: "روزگار",
  },
  "marital status": {
    hi: "वैवाहिक स्थिति", mr: "वैवाहिक स्थिती", bn: "বৈবাহিক অবস্থা",
    ta: "திருமண நிலை", te: "వైవాహిక స్థితి", gu: "વૈવાહિક સ્થિતિ",
    kn: "ವೈವಾಹಿಕ ಸ್ಥಿತಿ", ml: "വൈവാഹിക നില", pa: "ਵਿਆਹੁਤਾ ਸਥਿਤੀ",
    or: "ବୈବାହିକ ସ୍ଥିତି", as: "বৈবাহিক অৱস্থা", ur: "ازدواجی حیثیت",
  },
  "family income": {
    hi: "घर की आय", mr: "घरचे उत्पन्न", bn: "পরিবারের আয়",
    ta: "குடும்ப வருமானம்", te: "కుటుంబ ఆదాయం", gu: "ઘરની આવક",
    kn: "ಕುಟುಂಬದ ಆದಾಯ", ml: "കുടുംബ വരുമാനം", pa: "ਘਰ ਦੀ ਆਮਦਨ",
    or: "ପରିବାରର ଆୟ", as: "পৰিয়ালৰ আয়", ur: "گھر کی آمدنی",
  },
  land: {
    hi: "ज़मीन", mr: "जमीन", bn: "জমি", ta: "நிலம்", te: "భూమి", gu: "જમીન",
    kn: "ಭೂಮಿ", ml: "ഭൂമി", pa: "ਜ਼ਮੀਨ", or: "ଜମି", as: "মাটি", ur: "زمین",
  },
  BPL: {
    hi: "बीपीएल", mr: "बीपीएल", bn: "বিপিএল", ta: "வறுமைக் கோட்டுக்குக் கீழ்",
    te: "బీపీఎల్", gu: "બીપીએલ", kn: "ಬಿಪಿಎಲ್", ml: "ബിപിഎൽ", pa: "ਬੀਪੀਐਲ",
    or: "ବିପିଏଲ", as: "বিপিএল", ur: "بی پی ایل",
  },
  disability: {
    hi: "दिव्यांगता", mr: "दिव्यांगत्व", bn: "প্রতিবন্ধকতা", ta: "மாற்றுத்திறன்",
    te: "వైకల్యం", gu: "દિવ્યાંગતા", kn: "ಅಂಗವೈಕಲ್ಯ", ml: "ഭിന്നശേഷി",
    pa: "ਅਪੰਗਤਾ", or: "ଦିବ୍ୟାଙ୍ଗତା", as: "দিব্যাংগতা", ur: "معذوری",
  },
  student: {
    hi: "विद्यार्थी", mr: "विद्यार्थी", bn: "ছাত্রছাত্রী", ta: "மாணவர்",
    te: "విద్యార్థి", gu: "વિદ્યાર્થી", kn: "ವಿದ್ಯಾರ್ಥಿ", ml: "വിദ്യാർത്ഥി",
    pa: "ਵਿਦਿਆਰਥੀ", or: "ଛାତ୍ର", as: "ছাত্ৰ", ur: "طالب علم",
  },
  minority: {
    hi: "अल्पसंख्यक", mr: "अल्पसंख्याक", bn: "সংখ্যালঘু", ta: "சிறுபான்மையினர்",
    te: "మైనారిటీ", gu: "લઘુમતી", kn: "ಅಲ್ಪಸಂಖ್ಯಾತ", ml: "ന്യൂനപക്ഷം",
    pa: "ਘੱਟਗਿਣਤੀ", or: "ସଂଖ୍ୟାଲଘୁ", as: "সংখ্যালঘু", ur: "اقلیت",
  },
  "economic distress": {
    hi: "आर्थिक संकट", mr: "आर्थिक संकट", bn: "আর্থিক সংকট",
    ta: "பொருளாதாரச் சிக்கல்", te: "ఆర్థిక ఇబ్బంది", gu: "આર્થિક સંકટ",
    kn: "ಆರ್ಥಿಕ ಸಂಕಷ್ಟ", ml: "സാമ്പത്തിക പ്രതിസന്ധി", pa: "ਆਰਥਿਕ ਸੰਕਟ",
    or: "ଆର୍ଥିକ ସଙ୍କଟ", as: "আৰ্থিক সংকট", ur: "معاشی تنگی",
  },
  "government employee": {
    hi: "सरकारी नौकरी", mr: "सरकारी नोकरी", bn: "সরকারি চাকরি",
    ta: "அரசுப் பணி", te: "ప్రభుత్వ ఉద్యోగం", gu: "સરકારી નોકરી",
    kn: "ಸರ್ಕಾರಿ ಉದ್ಯೋಗ", ml: "സർക്കാർ ജോലി", pa: "ਸਰਕਾਰੀ ਨੌਕਰੀ",
    or: "ସରକାରୀ ଚାକିରି", as: "চৰকাৰী চাকৰি", ur: "سرکاری ملازمت",
  },
};

/**
 * One reason, translated — and a list of them joined for a sentence.
 *
 * `occupation` is the exception the pass-through in `label()` exists for: the
 * engine forwards the corpus's own occupation strings unchanged when they are
 * not one of its known values, so an untranslated one arrives here and must
 * come out as itself.
 */
export const facetLabel = (lang: Lang, name: string) =>
  label(FACET_LABELS, lang, name);

/** Urdu is written in the Arabic script, which has its own comma. A Latin one
 *  in a right-to-left line is both wrong and visually jarring. */
const SEPARATOR: Partial<Record<Lang, string>> = { ur: "، " };

/**
 * Join things that are already in the reader's language.
 *
 * Separate from `facetList` because not every list is a list of facets. The
 * assistant's apply card lists the blanks left in a form, and it was joining
 * them with a hardcoded ", " — the same Latin comma in an Urdu line that
 * `SEPARATOR` exists to stop. Anything joining a list for a sentence should
 * come through here rather than write its own comma.
 */
export const listJoin = (lang: Lang, parts: string[]) =>
  parts.filter(Boolean).join(SEPARATOR[lang] ?? ", ");

export const facetList = (lang: Lang, names: string[]) =>
  listJoin(lang, names.map((n) => facetLabel(lang, n)));

/**
 * The document a photograph turned out to be.
 *
 * `src/documents.py` classifies against a closed set of sixteen labels
 * (`KNOWN_DOCUMENTS`) and the English label is the value: it is matched against
 * the scheme's own published document list, so translating the value would
 * silently stop it matching anything — the same trap `CATEGORY_LABELS` warns
 * about above.
 *
 * Only the label is translated. Without this, `documents.ticked` rendered as
 * "यह आपका Aadhaar card लगता है। टिक कर दिया।" — the sentence in Hindi and the
 * thing it was about in English, at the moment someone is holding the document
 * up to a camera.
 *
 * Abbreviations and the names printed on the forms themselves stay as they are:
 * PAN, EPIC, UDID, khatauni, 7/12, pahani. Those are what the paper says, and a
 * translated one sends someone to ask a clerk for a document that has no name.
 */
export const DOCUMENT_LABELS: Vocabulary = {
  "Aadhaar card": {
    hi: "आधार कार्ड", mr: "आधार कार्ड", bn: "আধার কার্ড", ta: "ஆதார் அட்டை",
    te: "ఆధార్ కార్డు", gu: "આધાર કાર્ડ", kn: "ಆಧಾರ್ ಕಾರ್ಡ್",
    ml: "ആധാർ കാർഡ്", pa: "ਆਧਾਰ ਕਾਰਡ", or: "ଆଧାର କାର୍ଡ", as: "আধাৰ কাৰ্ড",
    ur: "آدھار کارڈ",
  },
  "PAN card": {
    hi: "PAN कार्ड", mr: "PAN कार्ड", bn: "PAN কার্ড", ta: "PAN அட்டை",
    te: "PAN కార్డు", gu: "PAN કાર્ડ", kn: "PAN ಕಾರ್ಡ್", ml: "PAN കാർഡ്",
    pa: "PAN ਕਾਰਡ", or: "PAN କାର୍ଡ", as: "PAN কাৰ্ড", ur: "PAN کارڈ",
  },
  "Ration card": {
    hi: "राशन कार्ड", mr: "रेशन कार्ड", bn: "রেশন কার্ড", ta: "ரேஷன் அட்டை",
    te: "రేషన్ కార్డు", gu: "રાશન કાર્ડ", kn: "ಪಡಿತರ ಚೀಟಿ",
    ml: "റേഷൻ കാർഡ്", pa: "ਰਾਸ਼ਨ ਕਾਰਡ", or: "ରାଶନ କାର୍ଡ", as: "ৰেচন কাৰ্ড",
    ur: "راشن کارڈ",
  },
  "Voter ID (EPIC)": {
    hi: "मतदाता पहचान पत्र (EPIC)", mr: "मतदार ओळखपत्र (EPIC)",
    bn: "ভোটার পরিচয়পত্র (EPIC)", ta: "வாக்காளர் அடையாள அட்டை (EPIC)",
    te: "ఓటరు గుర్తింపు కార్డు (EPIC)", gu: "મતદાર ઓળખકાર્ડ (EPIC)",
    kn: "ಮತದಾರ ಗುರುತಿನ ಚೀಟಿ (EPIC)", ml: "വോട്ടർ തിരിച്ചറിയൽ കാർഡ് (EPIC)",
    pa: "ਵੋਟਰ ਸ਼ਨਾਖ਼ਤੀ ਕਾਰਡ (EPIC)", or: "ଭୋଟର ପରିଚୟ ପତ୍ର (EPIC)",
    as: "ভোটাৰ পৰিচয় পত্ৰ (EPIC)", ur: "ووٹر شناختی کارڈ (EPIC)",
  },
  "Caste certificate": {
    hi: "जाति प्रमाण पत्र", mr: "जातीचा दाखला", bn: "জাতি সনদপত্র",
    ta: "சாதி சான்றிதழ்", te: "కుల ధ్రువీకరణ పత్రం", gu: "જાતિ પ્રમાણપત્ર",
    kn: "ಜಾತಿ ಪ್ರಮಾಣಪತ್ರ", ml: "ജാതി സർട്ടിഫിക്കറ്റ്",
    pa: "ਜਾਤੀ ਸਰਟੀਫਿਕੇਟ", or: "ଜାତି ପ୍ରମାଣପତ୍ର", as: "জাতি প্ৰমাণপত্ৰ",
    ur: "ذات کا سرٹیفکیٹ",
  },
  "Income certificate": {
    hi: "आय प्रमाण पत्र", mr: "उत्पन्नाचा दाखला", bn: "আয়ের সনদপত্র",
    ta: "வருமானச் சான்றிதழ்", te: "ఆదాయ ధ్రువీకరణ పత్రం",
    gu: "આવક પ્રમાણપત્ર", kn: "ಆದಾಯ ಪ್ರಮಾಣಪತ್ರ", ml: "വരുമാന സർട്ടിഫിക്കറ്റ്",
    pa: "ਆਮਦਨ ਸਰਟੀਫਿਕੇਟ", or: "ଆୟ ପ୍ରମାଣପତ୍ର", as: "আয়ৰ প্ৰমাণপত্ৰ",
    ur: "آمدنی کا سرٹیفکیٹ",
  },
  "Domicile or residence certificate": {
    hi: "निवास प्रमाण पत्र", mr: "रहिवासी दाखला", bn: "বাসস্থানের সনদপত্র",
    ta: "வசிப்பிடச் சான்றிதழ்", te: "నివాస ధ్రువీకరణ పత్రం",
    gu: "રહેઠાણ પ્રમાણપત્ર", kn: "ವಾಸಸ್ಥಳ ಪ್ರಮಾಣಪತ್ರ",
    ml: "താമസ സർട്ടിഫിക്കറ്റ്", pa: "ਰਿਹਾਇਸ਼ੀ ਸਰਟੀਫਿਕੇਟ",
    or: "ବସବାସ ପ୍ରମାଣପତ୍ର", as: "নিবাসৰ প্ৰমাণপত্ৰ", ur: "رہائش کا سرٹیفکیٹ",
  },
  "Bank passbook": {
    hi: "बैंक पासबुक", mr: "बँक पासबुक", bn: "ব্যাঙ্কের পাসবই",
    ta: "வங்கி கணக்குப் புத்தகம்", te: "బ్యాంక్ పాస్‌బుక్",
    gu: "બૅન્ક પાસબુક", kn: "ಬ್ಯಾಂಕ್ ಪಾಸ್‌ಬುಕ್", ml: "ബാങ്ക് പാസ്ബുക്ക്",
    pa: "ਬੈਂਕ ਪਾਸਬੁੱਕ", or: "ବ୍ୟାଙ୍କ ପାସବୁକ", as: "বেংক পাছবুক",
    ur: "بینک پاس بک",
  },
  "Birth certificate": {
    hi: "जन्म प्रमाण पत्र", mr: "जन्म दाखला", bn: "জন্ম সনদপত্র",
    ta: "பிறப்புச் சான்றிதழ்", te: "జన్మ ధ్రువీకరణ పత్రం",
    gu: "જન્મ પ્રમાણપત્ર", kn: "ಜನನ ಪ್ರಮಾಣಪತ್ರ", ml: "ജനന സർട്ടിഫിക്കറ്റ്",
    pa: "ਜਨਮ ਸਰਟੀਫਿਕੇਟ", or: "ଜନ୍ମ ପ୍ରମାଣପତ୍ର", as: "জন্ম প্ৰমাণপত্ৰ",
    ur: "پیدائش کا سرٹیفکیٹ",
  },
  "Disability certificate": {
    hi: "दिव्यांगता प्रमाण पत्र", mr: "अपंगत्व दाखला",
    bn: "প্রতিবন্ধকতার সনদপত্র", ta: "மாற்றுத்திறன் சான்றிதழ்",
    te: "వికలాంగ ధ్రువీకరణ పత్రం", gu: "વિકલાંગતા પ્રમાણપત્ર",
    kn: "ಅಂಗವಿಕಲತೆ ಪ್ರಮಾಣಪತ್ರ", ml: "വൈകല്യ സർട്ടിഫിക്കറ്റ്",
    pa: "ਅਪੰਗਤਾ ਸਰਟੀਫਿਕੇਟ", or: "ଦିବ୍ୟାଙ୍ଗ ପ୍ରମାଣପତ୍ର",
    as: "অক্ষমতাৰ প্ৰমাণপত্ৰ", ur: "معذوری کا سرٹیفکیٹ",
  },
  "Land record (khatauni / 7-12 / pahani)": {
    hi: "भूमि अभिलेख (खतौनी / 7-12 / पहाणी)",
    mr: "जमिनीचा उतारा (खतौनी / 7-12 / पहाणी)",
    bn: "জমির নথি (khatauni / 7-12 / pahani)",
    ta: "நில ஆவணம் (khatauni / 7-12 / pahani)",
    te: "భూమి రికార్డు (khatauni / 7-12 / pahani)",
    gu: "જમીન રેકોર્ડ (khatauni / 7-12 / pahani)",
    kn: "ಭೂ ದಾಖಲೆ (khatauni / 7-12 / pahani)",
    ml: "ഭൂരേഖ (khatauni / 7-12 / pahani)",
    pa: "ਜ਼ਮੀਨ ਦਾ ਰਿਕਾਰਡ (khatauni / 7-12 / pahani)",
    or: "ଜମି ରେକର୍ଡ (khatauni / 7-12 / pahani)",
    as: "মাটিৰ নথি (khatauni / 7-12 / pahani)",
    ur: "زمین کا ریکارڈ (khatauni / 7-12 / pahani)",
  },
  "Marksheet or school certificate": {
    hi: "अंकपत्र या स्कूल प्रमाण पत्र", mr: "गुणपत्रक किंवा शाळेचा दाखला",
    bn: "মার্কশিট বা স্কুলের সনদপত্র",
    ta: "மதிப்பெண் பட்டியல் அல்லது பள்ளிச் சான்றிதழ்",
    te: "మార్కుల పత్రం లేదా పాఠశాల ధ్రువీకరణ పత్రం",
    gu: "માર્કશીટ અથવા શાળાનું પ્રમાણપત્ર",
    kn: "ಅಂಕಪಟ್ಟಿ ಅಥವಾ ಶಾಲಾ ಪ್ರಮಾಣಪತ್ರ",
    ml: "മാർക്ക് ലിസ്റ്റ് അല്ലെങ്കിൽ സ്കൂൾ സർട്ടിഫിക്കറ്റ്",
    pa: "ਮਾਰਕਸ਼ੀਟ ਜਾਂ ਸਕੂਲ ਸਰਟੀਫਿਕੇਟ",
    or: "ମାର୍କସିଟ କିମ୍ବା ସ୍କୁଲ ପ୍ରମାଣପତ୍ର",
    as: "মাৰ্কশীট বা স্কুলৰ প্ৰমাণপত্ৰ", ur: "مارک شیٹ یا اسکول کا سرٹیفکیٹ",
  },
  "Death certificate": {
    hi: "मृत्यु प्रमाण पत्र", mr: "मृत्यू दाखला", bn: "মৃত্যু সনদপত্র",
    ta: "இறப்புச் சான்றிதழ்", te: "మరణ ధ్రువీకరణ పత్రం",
    gu: "મૃત્યુ પ્રમાણપત્ર", kn: "ಮರಣ ಪ್ರಮಾಣಪತ್ರ", ml: "മരണ സർട്ടിഫിക്കറ്റ്",
    pa: "ਮੌਤ ਦਾ ਸਰਟੀਫਿਕੇਟ", or: "ମୃତ୍ୟୁ ପ୍ରମାଣପତ୍ର", as: "মৃত্যু প্ৰমাণপত্ৰ",
    ur: "موت کا سرٹیفکیٹ",
  },
  Photograph: {
    hi: "फोटो", mr: "फोटो", bn: "ছবি", ta: "புகைப்படம்", te: "ఫోటో",
    gu: "ફોટો", kn: "ಫೋಟೋ", ml: "ഫോട്ടോ", pa: "ਫੋਟੋ", or: "ଫଟୋ",
    as: "ফটো", ur: "تصویر",
  },
  "Driving licence": {
    hi: "ड्राइविंग लाइसेंस", mr: "वाहन परवाना", bn: "ড্রাইভিং লাইসেন্স",
    ta: "ஓட்டுநர் உரிமம்", te: "డ్రైవింగ్ లైసెన్స్", gu: "ડ્રાઇવિંગ લાઇસન્સ",
    kn: "ಚಾಲನಾ ಪರವಾನಗಿ", ml: "ഡ്രൈവിങ് ലൈസൻസ്", pa: "ਡਰਾਈਵਿੰਗ ਲਾਇਸੈਂਸ",
    or: "ଡ୍ରାଇଭିଂ ଲାଇସେନ୍ସ", as: "ড্ৰাইভিং লাইচেন্স", ur: "ڈرائیونگ لائسنس",
  },
  "Labour or worker card": {
    hi: "श्रमिक कार्ड (e-Shram)", mr: "कामगार कार्ड (e-Shram)",
    bn: "শ্রমিক কার্ড (e-Shram)", ta: "தொழிலாளர் அட்டை (e-Shram)",
    te: "కార్మిక కార్డు (e-Shram)", gu: "શ્રમિક કાર્ડ (e-Shram)",
    kn: "ಕಾರ್ಮಿಕ ಕಾರ್ಡ್ (e-Shram)", ml: "തൊഴിലാളി കാർഡ് (e-Shram)",
    pa: "ਮਜ਼ਦੂਰ ਕਾਰਡ (e-Shram)", or: "ଶ୍ରମିକ କାର୍ଡ (e-Shram)",
    as: "শ্ৰমিক কাৰ্ড (e-Shram)", ur: "مزدور کارڈ (e-Shram)",
  },
};

export const documentLabel = (lang: Lang, name: string) =>
  label(DOCUMENT_LABELS, lang, name);
