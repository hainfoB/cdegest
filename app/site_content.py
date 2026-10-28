# -*- coding: utf-8 -*-
"""Contenus éditoriaux du site public, en arabe, français et anglais."""

def pick(d, lang):
    return d.get(lang) or d["fr"]


INSCRIPTION = {
    "fr": {
        "title": "Comment s'inscrire",
        "lead": "L'inscription est gratuite, se fait en ligne en moins de cinq minutes et ne demande aucun déplacement. Votre demande est ensuite étudiée par le CDE de votre wilaya.",
        "steps": [
            ("Préparation entrepreneuriale", "Répondez par oui ou non à six questions sur votre projet. Elles servent à vous orienter vers la formation la plus utile : découverte, compétences, création prochaine ou projet prêt."),
            ("Identité et contact", "Saisissez votre nom, votre téléphone et votre wilaya. Le CDE vous contactera sur ce numéro : vérifiez-le bien."),
            ("Formation et projet", "Indiquez votre situation (stagiaire ou diplômé), votre spécialité, le secteur visé et, si vous en avez une, votre idée de projet."),
            ("Choix du CDE et envoi", "Choisissez le CDE de votre wilaya, acceptez l'utilisation de vos données et envoyez. Conservez le numéro de suivi affiché."),
        ],
        "after_t": "Après l'envoi",
        "after": [
            "Votre demande a le statut « nouvelle » : le CDE l'étudie pendant la période d'inscription de la prochaine session.",
            "Chaque session de 10 jours accueille jusqu'à 150 stagiaires ; le CDE valide les inscriptions avant le démarrage.",
            "Si vous êtes retenu, vous recevez votre ticket : planning, groupe et code QR. Gardez le lien de suivi.",
            "Si vous n'êtes pas retenu cette fois, votre demande peut être reportée à une session suivante.",
        ],
        "need_t": "Ce qu'il vous faut",
        "need": ["Un téléphone joignable", "Votre spécialité ou votre diplôme de la formation professionnelle", "Quelques mots sur votre idée de projet (facultatif)"],
    },
    "ar": {
        "title": "كيفية التسجيل",
        "lead": "التسجيل مجاني ويتم عبر الإنترنت في أقل من خمس دقائق دون أي تنقل. بعد ذلك يدرس مركز تطوير المقاولاتية في ولايتك طلبك.",
        "steps": [
            ("الاستعداد المقاولاتي", "أجب بنعم أو لا عن ستة أسئلة حول مشروعك. تساعد على توجيهك نحو التكوين الأنسب: اكتشاف، كفاءات، إنشاء قريب أو مشروع جاهز."),
            ("الهوية والاتصال", "أدخل اسمك ورقم هاتفك وولايتك. سيتصل بك المركز على هذا الرقم، فتأكد منه جيدا."),
            ("التكوين والمشروع", "حدد وضعيتك (متربص أو متخرج) وتخصصك والقطاع المستهدف، وفكرة مشروعك إن وجدت."),
            ("اختيار المركز والإرسال", "اختر مركز ولايتك ووافق على استعمال معطياتك ثم أرسل. احتفظ برقم المتابعة الذي يظهر."),
        ],
        "after_t": "بعد الإرسال",
        "after": [
            "يكون طلبك في حالة «جديد»: يدرسه المركز خلال فترة التسجيل في الدورة القادمة.",
            "تستقبل كل دورة مدتها 10 أيام ما يصل إلى 150 متربصا، ويصادق المركز على التسجيلات قبل الانطلاق.",
            "إذا تم قبولك تتلقى تذكرتك: البرنامج والفوج ورمز QR. احتفظ برابط المتابعة.",
            "إذا لم يتم قبولك هذه المرة يمكن تأجيل طلبك إلى دورة لاحقة.",
        ],
        "need_t": "ما تحتاجه",
        "need": ["هاتف يمكن الاتصال بك عليه", "تخصصك أو شهادتك في التكوين المهني", "بضع كلمات عن فكرة مشروعك (اختياري)"],
    },
    "en": {
        "title": "How to register",
        "lead": "Registration is free, done online in under five minutes, with no travel. Your application is then reviewed by the CDE of your wilaya.",
        "steps": [
            ("Entrepreneurial readiness", "Answer six yes/no questions about your project. They help direct you to the most useful course: discovery, skills, upcoming start-up or ready project."),
            ("Identity and contact", "Enter your name, phone number and wilaya. The CDE will call you on this number: check it carefully."),
            ("Training and project", "State your situation (trainee or graduate), your specialty, the target sector and your project idea if you have one."),
            ("CDE choice and submission", "Choose the CDE of your wilaya, accept the use of your data and submit. Keep the tracking number shown."),
        ],
        "after_t": "After submitting",
        "after": [
            "Your application is “new”: the CDE reviews it during the registration period of the next session.",
            "Each 10-day session takes up to 150 trainees; the CDE validates registrations before the start.",
            "If selected, you receive your ticket: schedule, group and QR code. Keep the tracking link.",
            "If not selected this time, your application can be carried over to a later session.",
        ],
        "need_t": "What you need",
        "need": ["A phone number you can be reached on", "Your vocational training specialty or diploma", "A few words about your project idea (optional)"],
    },
}

FORMATION = {
    "fr": {
        "title": "La formation au CDE",
        "lead": "Le Centre de développement de l'entrepreneuriat forme gratuitement les stagiaires et les diplômés de la formation professionnelle à la création d'entreprise, en sessions intensives de 10 jours.",
        "cycle_t": "Le déroulement d'une session",
        "cycle": [
            ("Inscription", "Environ 10 jours avant chaque session, en ligne."),
            ("Validation des inscriptions", "Le CDE retient jusqu'à 150 stagiaires par session et constitue les groupes."),
            ("Formation et présence", "10 jours, deux séances par jour ; l'enseignant fait l'appel à chaque séance."),
            ("Clôture et validation", "La présence est contrôlée et validée par la NESDA."),
            ("Attestation", "Le représentant NESDA imprime votre attestation bilingue, vérifiable par code QR."),
        ],
        "themes_t": "Ce que vous apprenez",
        "themes": ["Trouver et tester une idée d'affaires", "Étudier son marché", "Construire son modèle d'affaires (Business Model Canvas)", "Rédiger son plan d'affaires", "Démarches juridiques et administratives", "Gestion financière de la micro-entreprise", "Marketing digital", "Présenter son projet (pitch)", "Dispositifs d'appui à la création d'entreprise"],
        "rules_t": "Les règles",
        "rules": [
            "L'attestation est délivrée si votre assiduité atteint au moins 80 % des séances.",
            "Deux absences consécutives non justifiées signalent un abandon.",
            "Une séance annulée par absence de l'enseignant n'est pas comptée contre vous : elle est reprogrammée.",
            "Après la formation, la NESDA peut vous accompagner pour monter votre projet.",
        ],
    },
    "ar": {
        "title": "التكوين في مركز تطوير المقاولاتية",
        "lead": "يكوّن مركز تطوير المقاولاتية مجانا المتربصين وخريجي التكوين المهني على إنشاء المؤسسات، في دورات مكثفة مدتها 10 أيام.",
        "cycle_t": "مراحل الدورة",
        "cycle": [
            ("التسجيل", "عبر الإنترنت، حوالي 10 أيام قبل كل دورة."),
            ("المصادقة على التسجيلات", "يختار المركز ما يصل إلى 150 متربصا لكل دورة ويشكل الأفواج."),
            ("التكوين والحضور", "10 أيام بحصتين يوميا، ويسجل الأستاذ الحضور في كل حصة."),
            ("الاختتام والمصادقة", "تراقب الوكالة الوطنية لدعم وتنمية المقاولاتية الحضور وتصادق عليه."),
            ("الشهادة", "يطبع ممثل الوكالة شهادتك ثنائية اللغة، القابلة للتحقق برمز QR."),
        ],
        "themes_t": "ما ستتعلمه",
        "themes": ["إيجاد فكرة مشروع واختبارها", "دراسة السوق", "بناء نموذج العمل", "إعداد مخطط الأعمال", "الإجراءات القانونية والإدارية", "التسيير المالي للمؤسسة المصغرة", "التسويق الرقمي", "عرض المشروع", "أجهزة دعم إنشاء المؤسسات"],
        "rules_t": "القواعد",
        "rules": [
            "تمنح الشهادة إذا بلغت نسبة حضورك 80 ٪ على الأقل من الحصص.",
            "غيابان متتاليان دون مبرر يعتبران تخليا.",
            "الحصة الملغاة بسبب غياب الأستاذ لا تحتسب ضدك، وتعاد برمجتها.",
            "بعد التكوين يمكن للوكالة مرافقتك لإنجاز مشروعك.",
        ],
    },
    "en": {
        "title": "Training at the CDE",
        "lead": "The Entrepreneurship Development Centre trains vocational trainees and graduates in starting a business, free of charge, in intensive 10-day sessions.",
        "cycle_t": "How a session runs",
        "cycle": [
            ("Registration", "Online, about 10 days before each session."),
            ("Registration validation", "The CDE selects up to 150 trainees per session and forms the groups."),
            ("Training and attendance", "10 days, two classes a day; the teacher takes attendance at each class."),
            ("Closing and validation", "Attendance is checked and validated by NESDA."),
            ("Certificate", "The NESDA representative prints your bilingual certificate, verifiable by QR code."),
        ],
        "themes_t": "What you learn",
        "themes": ["Finding and testing a business idea", "Market research", "Business Model Canvas", "Writing a business plan", "Legal and administrative steps", "Small business finance", "Digital marketing", "Pitching your project", "Start-up support schemes"],
        "rules_t": "The rules",
        "rules": [
            "The certificate is issued if you attend at least 80 % of the classes.",
            "Two consecutive unjustified absences signal a dropout.",
            "A class cancelled because the teacher is absent does not count against you: it is rescheduled.",
            "After the training, NESDA can support you in setting up your project.",
        ],
    },
}

FAQ = {
    "fr": [
        ("Inscription", [
            ("L'inscription est-elle payante ?", "Non. L'inscription et la formation sont entièrement gratuites."),
            ("Qui peut s'inscrire ?", "Les stagiaires et les diplômés de la formation professionnelle qui veulent créer leur entreprise ou découvrir l'entrepreneuriat."),
            ("Je me suis trompé dans mes informations. Que faire ?", "Envoyez un signalement de catégorie « Inscription » avec votre numéro de suivi : le CDE corrigera votre dossier."),
            ("Comment savoir si ma demande est retenue ?", "Ouvrez le lien de suivi reçu à l'envoi : il affiche l'état de votre demande puis votre ticket une fois retenu. Le CDE vous appelle aussi."),
            ("Pourquoi ma demande n'a-t-elle pas été retenue ?", "Chaque session accueille jusqu'à 150 stagiaires alors que le CDE reçoit souvent beaucoup plus de demandes. Votre demande peut être proposée pour une session suivante."),
        ]),
        ("Formation", [
            ("Combien de temps dure une formation ?", "Une session dure 10 jours, à raison de deux séances par jour."),
            ("Puis-je suivre la formation pendant mon stage pratique ?", "Oui. Les stagiaires en stage pratique sont inscrits directement par leur établissement auprès du CDE."),
            ("Que se passe-t-il si je manque une séance ?", "Prévenez le CDE. Une absence justifiée est enregistrée comme excusée ; au-delà de 20 % d'absences, l'attestation n'est pas délivrée."),
        ]),
        ("Attestation et suite", [
            ("Qui délivre l'attestation ?", "Après le contrôle de la présence, le représentant de la NESDA de votre wilaya valide et imprime l'attestation."),
            ("Comment prouver que mon attestation est authentique ?", "Chaque attestation porte un numéro et un code QR ; la page « Vérifier une attestation » confirme son authenticité."),
            ("Et après la formation ?", "La NESDA peut vous accompagner pour monter votre dossier et financer votre projet."),
        ]),
        ("Compte et données", [
            ("Mes données sont-elles protégées ?", "Oui. Elles sont utilisées uniquement par le CDE, la DFEP, le MFEP et la NESDA pour le suivi de la formation, conformément à la loi n° 18-07."),
            ("Je n'arrive pas à me connecter (agents)", "Utilisez « Signaler un problème », catégorie « Compte et connexion » : votre responsable ou l'administrateur réinitialisera votre accès."),
        ]),
    ],
    "ar": [
        ("التسجيل", [
            ("هل التسجيل بمقابل؟", "لا. التسجيل والتكوين مجانيان تماما."),
            ("من يمكنه التسجيل؟", "متربصو وخريجو التكوين المهني الراغبون في إنشاء مؤسستهم أو اكتشاف المقاولاتية."),
            ("أخطأت في معلوماتي، ماذا أفعل؟", "أرسل بلاغا من فئة «التسجيل» مع رقم المتابعة، وسيصحح المركز ملفك."),
            ("كيف أعرف أن طلبي قُبل؟", "افتح رابط المتابعة الذي تلقيته عند الإرسال: يعرض حالة طلبك ثم تذكرتك عند القبول. كما يتصل بك المركز."),
            ("لماذا لم يُقبل طلبي؟", "تستقبل كل دورة ما يصل إلى 150 متربصا بينما يتلقى المركز غالبا طلبات أكثر بكثير. يمكن اقتراح طلبك لدورة لاحقة."),
        ]),
        ("التكوين", [
            ("كم تدوم الدورة؟", "تدوم الدورة 10 أيام بمعدل حصتين يوميا."),
            ("هل يمكنني متابعة التكوين أثناء التربص التطبيقي؟", "نعم. يسجل المتربصون في التربص التطبيقي مباشرة من طرف مؤسستهم لدى المركز."),
            ("ماذا يحدث إذا غبت عن حصة؟", "أبلغ المركز. يسجل الغياب المبرر كغياب معذور، وإذا تجاوز الغياب 20 ٪ لا تمنح الشهادة."),
        ]),
        ("الشهادة وما بعدها", [
            ("من يسلم الشهادة؟", "بعد مراقبة الحضور يصادق ممثل الوكالة الوطنية لدعم وتنمية المقاولاتية في ولايتك على الشهادة ويطبعها."),
            ("كيف أثبت صحة شهادتي؟", "تحمل كل شهادة رقما ورمز QR، وتؤكد صفحة «التحقق من شهادة» صحتها."),
            ("وبعد التكوين؟", "يمكن للوكالة مرافقتك لإعداد ملفك وتمويل مشروعك."),
        ]),
        ("الحساب والمعطيات", [
            ("هل معطياتي محمية؟", "نعم. لا تستعمل إلا من طرف المركز ومديرية التكوين والوزارة والوكالة لمتابعة التكوين، وفقا للقانون 18-07."),
            ("لا أستطيع الدخول (الأعوان)", "استعمل «الإبلاغ عن مشكل» فئة «الحساب والدخول»، وسيعيد مسؤولك أو المسؤول التقني تفعيل دخولك."),
        ]),
    ],
    "en": [
        ("Registration", [
            ("Is registration free?", "Yes. Registration and training are entirely free."),
            ("Who can register?", "Vocational trainees and graduates who want to start a business or discover entrepreneurship."),
            ("I made a mistake in my details. What should I do?", "Send a report in the “Registration” category with your tracking number: the CDE will correct your file."),
            ("How do I know if I was selected?", "Open the tracking link received on submission: it shows your status, then your ticket once selected. The CDE also calls you."),
            ("Why was my application not selected?", "Each session takes up to 150 trainees while the CDE often receives many more applications. Yours can be offered for a later session."),
        ]),
        ("Training", [
            ("How long is a course?", "A session lasts 10 days, with two classes a day."),
            ("Can I attend during my internship?", "Yes. Trainees on internship are registered directly by their institution with the CDE."),
            ("What if I miss a class?", "Tell the CDE. A justified absence is recorded as excused; above 20 % absences the certificate is not issued."),
        ]),
        ("Certificate and next steps", [
            ("Who issues the certificate?", "After the attendance check, the NESDA representative of your wilaya validates and prints the certificate."),
            ("How can I prove my certificate is genuine?", "Each certificate has a number and a QR code; the “Verify a certificate” page confirms it."),
            ("And after the training?", "NESDA can help you prepare your file and finance your project."),
        ]),
        ("Account and data", [
            ("Is my data protected?", "Yes. It is used only by the CDE, DFEP, MFEP and NESDA to follow the training, in line with law 18-07."),
            ("I cannot log in (staff)", "Use “Report a problem”, category “Account and login”: your manager or the administrator will reset your access."),
        ]),
    ],
}

TICKET_CATS = ("inscription", "compte", "session", "presence", "attestation", "technique", "autre")
EVENT_KINDS = ("evenement", "portes_ouvertes", "salon", "concours", "annonce")
