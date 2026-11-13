"""Logique RH (RAG, prompt, sources, helpers) extraite de l'application.

Ce module contient l'implémentation historique de `app_rh` afin de préserver
le comportement et les API publiques testées, tout en permettant une
intégration dans le portail modulaire.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ingest import (
    CHROMA_DIR,
    EMBEDDING_MODEL,
    MANIFESTE_INGESTION,
    OLLAMA_BASE_URL,
    creer_embeddings,
)
from pieces_jointes import IndexPiecesJointes

logger = logging.getLogger(__name__)

# Configuration
APP_VERSION = "1.1.0"
LLM_MODEL = os.getenv("ASSISTANT_DRH_MODEL", "llama3.2")
TOP_K = 8
FETCH_K = 40
MMR_LAMBDA = 0.7
FACTEUR_CANDIDATS = 4
HISTORIQUE_MAX_MESSAGES = 6
HISTORIQUE_MAX_CARACTERES = 6000
CATEGORIE_ODOO = "odoo"
CATEGORIE_CONVENTION = "convention"
MOTS_CLES_ODOO = ("odoo", "pgi")
MOTS_CLES_CONVENTION = (
    "restauration rapide",
    "restaurant",
    "hee",
    "convention collective",
    "idcc 1501",
    "grille",
    "prime",
)
MOTS_CLES_RGPD = (
    "rgpd",
    "donnees personnelles",
    "cnil",
    "protection des donnees",
    "informatique et libertes",
)
MOTS_CLES_RSE = (
    "rse",
    "responsabilite societale",
    "diversite",
    "developpement durable",
    "environnement",
)
SOURCES_HORS_SUJET = (
    ("cnil.fr", MOTS_CLES_RGPD),
    ("bpifrance-creation.fr", MOTS_CLES_RSE),
    (
        "economie.gouv.fr/entreprises/gerer-son-entreprise-au-quotidien",
        MOTS_CLES_RSE,
    ),
)
MODULES_ODOO = {
    "conge": "time_off",
    "absence": "time_off",
    "pointage": "attendances",
    "presence": "attendances",
    "recrutement": "recruitment",
    "candidat": "recruitment",
    "entretien": "appraisals",
    "evaluation": "appraisals",
    "paie": "payroll",
    "salaire": "payroll",
    "employe": "employees",
}
SOURCES_ODOO = {
    "time_off": "https://www.odoo.com/documentation/20.0/applications/hr/time_off.html",
    "attendances": "https://www.odoo.com/documentation/20.0/applications/hr/attendances.html",
    "recruitment": "https://www.odoo.com/documentation/20.0/applications/hr/recruitment.html",
    "appraisals": "https://www.odoo.com/documentation/20.0/applications/hr/appraisals.html",
    "payroll": "https://www.odoo.com/documentation/20.0/applications/hr/payroll.html",
    "employees": "https://www.odoo.com/documentation/20.0/applications/hr/employees.html",
}
LLM_TEMPERATURE = 0.0
LLM_NUM_CTX = 8192

MESSAGE_SANS_RESULTAT = (
    "Je ne trouve pas cette information dans la base documentaire "
    "(Code du travail, convention collective de la restauration rapide, "
    "referentiels RH et documentation Odoo). Precisez votre question, ou "
    "joignez le document concerne pour que je puisse y repondre."
)

LANGUES = {
    "fr": {
        "nom": "Français",
        "consigne": (
            "Reponds en francais, de facon claire, concise et structuree. "
            "Redige toute la reponse dans cette langue, y compris les titres."
        ),
    },
    "en": {
        "nom": "English",
        "consigne": (
            "Answer in English, clearly, concisely and in a structured way. "
            "Write the whole answer in that language, headings included."
        ),
    },
    "ko": {
        "nom": "한국어",
        "consigne": (
            "한국어로 명확하고 간결하게, 체계적으로 답하세요. "
            "제목을 포함한 답변 전체를 한국어로 작성하세요."
        ),
    },
}
LANGUE_DEFAUT = "fr"

MESSAGES_SANS_RESULTAT = {
    "fr": MESSAGE_SANS_RESULTAT,
    "en": (
        "I cannot find this information in the documentary base (French Labour "
        "Code, fast-food collective agreement, HR reference documents and Odoo "
        "documentation). Please refine your question, or attach the relevant "
        "document so that I can answer it."
    ),
    "ko": (
        "문서 기반(프랑스 노동법, 패스트푸드 단체협약, 인사 참고자료 및 Odoo "
        "문서)에서 해당 정보를 찾을 수 없습니다. 질문을 더 구체적으로 "
        "작성하거나 관련 문서를 첨부해 주시면 답변드릴 수 있습니다."
    ),
}


def normaliser_langue(langue: str | None) -> str:
    """Ramene un code de langue inconnu ou absent au francais."""
    return langue if langue in LANGUES else LANGUE_DEFAUT


PROMPTS_PAR_LANGUE = {
    "fr": (
        "Tu es le DRH strategique et operationnel des restaurants du groupe HEE, "
        "convention collective de la restauration rapide. Tu es expert sur le PGI "
        "Odoo. Tu es le garant de la culture d'entreprise, de la performance des "
        "equipes et du respect du droit du travail francais.\n"
        "Tu couvres l'ensemble des domaines RH : recrutement et integration, "
        "contrats (CDI, CDD, contrat d'extra, apprentissage, interim), temps de "
        "travail et conges, paie et avantages, absences et sante, discipline et "
        "rupture du contrat, formation et competences, entretiens et performance, "
        "dialogue social, sante et securite au travail, RSE et diversite, "
        "protection des donnees personnelles, ainsi que les modules RH du PGI "
        "Odoo (employes, conges, pointage, paie, recrutement, entretiens).\n"
        "{consigne_langue}\n\n"
        "Regles :\n"
        "- Utilise uniquement le CONTEXTE ci-dessous et, pour comprendre la "
        "question, l'HISTORIQUE RECENT. Ne considere jamais l'historique comme "
        "une source de faits.\n"
        "- Si la question porte sur plusieurs sujets, reponds point par point.\n"
        "- Distingue, quand le contexte le permet, ce qui releve de la loi, de la "
        "convention collective de la restauration rapide (IDCC 1501) et des "
        "documents internes.\n"
        "- Pour une question Odoo, precise le module et le chemin de menu lorsque "
        "le contexte les fournit.\n"
        "- Si le contexte ne contient pas la reponse, dis-le explicitement, "
        "indique ce qui manque et propose une demarche ou une source a consulter.\n"
        "- N'invente aucune information juridique, chiffree ou procedurale.\n"
        "- Chaque affirmation factuelle doit etre appuyee par une source [n] du "
        "CONTEXTE.\n"
        "- Ne cite jamais un numero d'article, un montant, une date ou un chemin "
        "de menu qui n'apparait pas textuellement dans le contexte : ecris "
        "\"non precise dans les sources\".\n"
        "- Pour les montants, precise la date et le perimetre (metropole / "
        "Mayotte) ; utilise le cas general sauf demande contraire.\n"
        "- Pour une relance, reponds au point demande en t'appuyant sur la "
        "question precedente, sans repeter inutilement la reponse precedente.\n"
        "- Cite les sources avec leur numero entre crochets, par exemple [1].\n"
        "- Les extraits marques \"Piece jointe\" proviennent des fichiers fournis "
        "par l'utilisateur ; les autres viennent de la base RH.\n"
        "- Si le contexte ne contient que des pieces jointes, fonde la reponse "
        "exclusivement sur celles-ci.\n\n"
        "HISTORIQUE RECENT :\n{historique}\n\n"
        "CONTEXTE :\n{contexte}\n\n"
        "QUESTION : {question}\n\n"
        "REPONSE :"
    ),
    "en": (
        "You are the strategic and operational HR director of the HEE restaurant "
        "group, covered by the French fast-food collective agreement. You are an "
        "expert in the Odoo ERP. You are responsible for company culture, team "
        "performance and compliance with French labour law.\n"
        "You cover every HR domain: recruitment and onboarding, contracts "
        "(permanent, fixed-term, extra shifts, apprenticeship, temporary work), "
        "working time and leave, pay and benefits, absences and health, discipline "
        "and termination, training and skills, appraisals and performance, employee "
        "relations, health and safety, CSR and diversity, personal data protection, "
        "and the HR modules of the Odoo ERP (employees, time off, attendance, "
        "payroll, recruitment, appraisals).\n"
        "{consigne_langue}\n\n"
        "Rules:\n"
        "- Use only the CONTEXT below and, to understand the question, the RECENT "
        "HISTORY. Never treat the history as a source of facts.\n"
        "- If the question covers several topics, answer point by point.\n"
        "- When the context allows, distinguish between statute law, the French "
        "fast-food collective agreement (IDCC 1501) and internal documents.\n"
        "- For an Odoo question, state the module and the menu path when the "
        "context provides them.\n"
        "- If the context does not contain the answer, say so explicitly, state "
        "what is missing and suggest an approach or a source to consult.\n"
        "- Do not invent any legal, numerical or procedural information.\n"
        "- Every factual statement must be supported by a source [n] from the "
        "CONTEXT.\n"
        "- Never cite an article number, amount, date or menu path that does not "
        "appear verbatim in the context: write \"not specified in the sources\".\n"
        "- For amounts, state the date and scope (mainland France / Mayotte); use "
        "the general case unless asked otherwise.\n"
        "- For a follow-up question, answer the point asked using the previous "
        "question, without needlessly repeating the previous answer.\n"
        "- Cite sources with their number in brackets, for example [1].\n"
        "- Excerpts marked \"Piece jointe\" come from files supplied by the user; "
        "the others come from the HR database.\n"
        "- If the context contains only attachments, base the answer exclusively "
        "on them.\n\n"
        "RECENT HISTORY:\n{historique}\n\n"
        "CONTEXT:\n{contexte}\n\n"
        "QUESTION: {question}\n\n"
        "ANSWER (in English only):"
    ),
    "ko": (
        "당신은 HEE 레스토랑 그룹의 전략적·운영적 인사 담당 이사이며, 프랑스 "
        "패스트푸드 단체협약의 적용을 받습니다. 당신은 Odoo ERP 전문가입니다. "
        "기업 문화, 팀 성과, 프랑스 노동법 준수를 책임집니다.\n"
        "당신은 모든 인사 영역을 다룹니다: 채용과 온보딩, 계약(정규직, 기간제, "
        "단기 대체근무, 도제, 파견), 근로시간과 휴가, 급여와 복리후생, 결근과 "
        "건강, 징계와 계약 해지, 교육과 역량, 면담과 성과, 노사 관계, "
        "산업안전보건, CSR과 다양성, 개인정보 보호, 그리고 Odoo ERP의 인사 "
        "모듈(직원, 휴가, 출퇴근, 급여, 채용, 면담)입니다.\n"
        "{consigne_langue}\n\n"
        "규칙:\n"
        "- 아래 CONTEXT와 질문 이해를 위한 최근 대화 기록만 사용하십시오. "
        "대화 기록을 사실의 출처로 삼지 마십시오.\n"
        "- 질문이 여러 주제를 다루면 항목별로 답하십시오.\n"
        "- 문맥이 허락하는 경우 법률, 프랑스 패스트푸드 단체협약(IDCC 1501), "
        "내부 문서를 구분하십시오.\n"
        "- Odoo 관련 질문에는 문맥에 제시된 경우 모듈과 메뉴 경로를 "
        "명시하십시오.\n"
        "- 문맥에 답이 없으면 명확히 밝히고, 무엇이 부족한지 설명하며 확인할 "
        "방법이나 출처를 제안하십시오.\n"
        "- 법률, 수치, 절차에 관한 정보를 지어내지 마십시오.\n"
        "- 모든 사실 진술은 CONTEXT의 출처 [n]으로 뒷받침되어야 합니다.\n"
        "- 문맥에 그대로 나오지 않은 조항 번호, 금액, 날짜, 메뉴 경로를 "
        "인용하지 마십시오. 이 경우 \"출처에 명시되지 않음\"이라고 "
        "쓰십시오.\n"
        "- 금액은 날짜와 범위(프랑스 본토/마요트)를 명시하고, 별도 요청이 "
        "없으면 일반적인 경우를 사용하십시오.\n"
        "- 후속 질문에는 이전 질문을 활용해 요청한 사항에 답하고, 이전 답변을 "
        "불필요하게 반복하지 마십시오.\n"
        "- 출처는 대괄호와 번호로 인용하십시오(예: [1]).\n"
        "- \"Piece jointe\"로 표시된 발췌는 사용자가 제공한 파일에서, 나머지는 "
        "인사 데이터베이스에서 온 것입니다.\n"
        "- 문맥에 첨부 파일만 있으면 첨부 파일에만 근거하여 답하십시오.\n\n"
        "최근 대화 기록:\n{historique}\n\n"
        "CONTEXT:\n{contexte}\n\n"
        "질문: {question}\n\n"
        "답변(한국어로만):"
    ),
}
PROMPT_TEMPLATE = PROMPTS_PAR_LANGUE[LANGUE_DEFAUT]

ROLES_HISTORIQUE = {
    "fr": {"user": "UTILISATEUR", "assistant": "ASSISTANT"},
    "en": {"user": "USER", "assistant": "ASSISTANT"},
    "ko": {"user": "사용자", "assistant": "어시스턴트"},
}


def creer_vectorstore(
    persist_directory: str | Path = CHROMA_DIR,
    embeddings: Any | None = None,
) -> Any:
    """Ouvre la base ChromaDB existante avec les embeddings Ollama."""
    from langchain_chroma import Chroma

    if embeddings is None:
        embeddings = creer_embeddings()
    return Chroma(
        persist_directory=str(persist_directory),
        embedding_function=embeddings,
    )


def creer_llm(
    model: str = LLM_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    temperature: float = LLM_TEMPERATURE,
) -> Any:
    """Initialise le modele de langage local (llama3.2 par defaut)."""
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=model,
        base_url=base_url,
        temperature=temperature,
        num_ctx=LLM_NUM_CTX,
    )


def categorie_question(question: str) -> str | None:
    """Devine la famille de sources a interroger en priorite.

    Odoo et la convention collective de la restauration rapide sont
    sous-representes dans l'index (le Code du travail represente plus de
    80 % des chunks). Sans routage, une question Odoo ou « restauration
    rapide » peut etre noyee par les articles generaux.
    """
    question_minuscule = question.lower()
    if any(mot in question_minuscule for mot in MOTS_CLES_ODOO):
        return CATEGORIE_ODOO
    if any(mot in question_minuscule for mot in MOTS_CLES_CONVENTION):
        return CATEGORIE_CONVENTION
    return None


def _rechercher_mmr(question: str, vectorstore: Any, k: int) -> list[Any]:
    """Recherche MMR, avec repli sur la similarite simple."""
    mmr = getattr(vectorstore, "max_marginal_relevance_search", None)
    if callable(mmr):
        try:
            return list(
                mmr(
                    question,
                    k=k,
                    fetch_k=max(FETCH_K, k * 4),
                    lambda_mult=MMR_LAMBDA,
                )
            )
        except Exception as exc:  # noqa: BLE001 - repli obligatoire pour l'UI
            logger.warning("Recherche MMR indisponible, repli sur similarite : %s", exc)
    return list(vectorstore.similarity_search(question, k=k))


def _rechercher_filtre(
    question: str, vectorstore: Any, k: int, categorie: str
) -> list[Any]:
    """Recherche limitee a une categorie de sources, si le vectorstore le permet."""
    try:
        return list(
            vectorstore.similarity_search(
                question, k=k, filter={"categorie": categorie}
            )
        )
    except Exception as exc:  # noqa: BLE001 - un index ancien peut ignorer le filtre
        logger.warning(
            "Filtre de categorie %s indisponible, repli sans filtre : %s",
            categorie,
            exc,
        )
        return []


def module_odoo(question: str) -> str | None:
    """Devine le module Odoo concerne par la question."""
    question_minuscule = question.lower()
    for mot, module in MODULES_ODOO.items():
        if mot in question_minuscule:
            return module
    return None


def _prioriser_module_odoo(documents: list[Any], module: str | None) -> list[Any]:
    """Place les extraits du module Odoo attendu en tete, a pertinence egale."""
    if not module:
        return documents

    def cle(document: Any) -> int:
        source = str((getattr(document, "metadata", None) or {}).get("source") or "")
        return 0 if module in source else 1

    return sorted(documents, key=cle)


def _rechercher_source(
    question: str, vectorstore: Any, k: int, source: str
) -> list[Any]:
    """Recherche limitee a une source exacte (une page de documentation Odoo)."""
    try:
        documents = list(
            vectorstore.similarity_search(question, k=k, filter={"source": source})
        )
    except Exception as exc:  # noqa: BLE001 - index ancien ou filtre indisponible
        logger.warning("Filtre de source %s indisponible : %s", source, exc)
        return []
    return [
        document
        for document in documents
        if str((getattr(document, "metadata", None) or {}).get("source") or "")
        == source
    ]


def _cle_document(document: Any) -> tuple[str, str, str]:
    metadata = getattr(document, "metadata", None) or {}
    return (
        str(metadata.get("source") or ""),
        str(metadata.get("page") or ""),
        str(getattr(document, "page_content", ""))[:120],
    )


def _dedupliquer(documents: list[Any]) -> list[Any]:
    """Supprime les doublons par source, page et debut de contenu."""
    vus: set[tuple[str, str, str]] = set()
    resultat = []
    for document in documents:
        cle = _cle_document(document)
        if cle in vus:
            continue
        vus.add(cle)
        resultat.append(document)
    return resultat


_INDEX_LEXICAL: dict[int, Any] = {}


def _index_lexical(vectorstore: Any) -> Any:
    """Construit (une seule fois par vectorstore) l'index BM25 global."""
    cle = id(vectorstore)
    if cle not in _INDEX_LEXICAL:
        from recherche_lexicale import construire_index

        _INDEX_LEXICAL[cle] = construire_index(vectorstore)
    return _INDEX_LEXICAL[cle]


def _fusion_rrf(listes: list[list[Any]], k: int) -> list[Any]:
    """Fusionne des classements heterogenes par Reciprocal Rank Fusion."""
    scores: dict[tuple[str, str, str], float] = defaultdict(float)
    documents: dict[tuple[str, str, str], Any] = {}
    for documents_classes in listes:
        for rang, document in enumerate(documents_classes):
            cle = _cle_document(document)
            documents.setdefault(cle, document)
            scores[cle] += 1.0 / (60 + rang + 1)

    classement = sorted(scores, key=lambda cle: scores[cle], reverse=True)
    return [documents[cle] for cle in classement[:k]]


def _est_paratexte_convention(document: Any) -> bool:
    """Detecte les pages de garde, sommaires et arretes d'extension.

    Ces pages contiennent tous les mots cles de la convention (nom, IDCC,
    date) et remontent donc souvent a la place des articles utiles.
    """
    metadata = getattr(document, "metadata", None) or {}
    source = str(metadata.get("source") or "").lower()
    if "convention_collective" not in source:
        return False

    contenu = str(getattr(document, "page_content", "") or "").lower()
    if "sommaire" in contenu or "texte integral" in contenu:
        return True
    if "www.legisocial.fr" in contenu and "idcc" in contenu:
        return True

    try:
        page = int(metadata.get("page"))
    except (TypeError, ValueError):
        return False
    return page < 8 or page > 235


def _retirer_hors_sujet(question: str, documents: list[Any]) -> list[Any]:
    """Retire les sources specialisees quand la question ne les concerne pas.

    Sans cela, un passage CNIL sur le droit d'acces peut remonter sur une
    question d'arrete maladie, ou un passage RSE sur une question de paie.
    """
    question_minuscule = question.lower()
    prefixes_exclus = [
        prefixe
        for prefixe, mots_cles in SOURCES_HORS_SUJET
        if not any(mot in question_minuscule for mot in mots_cles)
    ]
    if not prefixes_exclus:
        return documents

    return [
        document
        for document in documents
        if not any(
            prefixe
            in str((getattr(document, "metadata", None) or {}).get("source") or "")
            for prefixe in prefixes_exclus
        )
    ]


def _recherche_hybride(question: str, vectorstore: Any, k: int) -> list[Any]:
    """Fusionne recherche semantique (MMR) et recherche lexicale (BM25)."""
    nombre_candidats = max(k * FACTEUR_CANDIDATS, 16)
    documents_semantiques = _rechercher_mmr(
        question, vectorstore, nombre_candidats
    )
    index = _index_lexical(vectorstore)
    documents_lexicaux = (
        index.rechercher(question, k=nombre_candidats) if index is not None else []
    )
    fusion = _fusion_rrf(
        [documents_semantiques, documents_lexicaux], nombre_candidats
    )
    filtres = _retirer_hors_sujet(question, fusion)
    filtres = [
        document
        for document in filtres
        if not _est_paratexte_convention(document)
    ]
    return (filtres or fusion)[:k]


def _completer_sources(
    documents: list[Any],
    vectorstore: Any,
    max_sources: int = 2,
    max_morceaux: int = 10,
) -> list[Any]:
    """Complete les extraits d'une meme source courte par tous ses morceaux.

    Un tableau de montants peut etre coupe entre deux morceaux : le morceau
    contenant le debut de la phrase est retrouve, pas celui qui contient les
    chiffres. Quand une source est courte (une page du Code du travail
    numerique, par exemple), on transmet l'ensemble de ses morceaux pour ne
    pas amputer la reponse.
    """
    get = getattr(vectorstore, "get", None)
    if not callable(get) or not documents:
        return documents

    occurrences = Counter(
        str((getattr(document, "metadata", None) or {}).get("source") or "")
        for document in documents
    )
    completions: dict[str, list[Any]] = {}
    for source, _ in occurrences.most_common(max_sources):
        if not source:
            continue
        try:
            donnees = get(
                where={"source": source},
                limit=max_morceaux + 1,
                include=["documents", "metadatas"],
            )
        except Exception as exc:  # noqa: BLE001 - la completion reste optionnelle
            logger.warning("Completion impossible pour %s : %s", source, exc)
            continue
        textes = donnees.get("documents") or []
        metadonnees = donnees.get("metadatas") or []
        if not textes or len(textes) > max_morceaux:
            continue
        from langchain_core.documents import Document

        completions[source] = [
            Document(page_content=texte or "", metadata=metadata or {})
            for texte, metadata in zip(textes, metadonnees)
        ]

    if not completions:
        return documents

    resultat: list[Any] = []
    vus: set[tuple[str, str, str]] = set()

    def ajouter(document: Any) -> None:
        cle = _cle_document(document)
        if cle in vus:
            return
        vus.add(cle)
        resultat.append(document)

    for document in documents:
        source = str((getattr(document, "metadata", None) or {}).get("source") or "")
        if source in completions:
            for morceau in completions[source]:
                ajouter(morceau)
            del completions[source]
        else:
            ajouter(document)
    return resultat


def rechercher(question: str, vectorstore: Any, k: int = TOP_K) -> list[Any]:
    """Retourne les extraits les plus pertinents, avec routage par famille.

    - Question Odoo : documentation Odoo en priorite, repli general si vide.
    - Question « restauration rapide » / convention : une partie des extraits
      est reservee a la convention collective, le reste a la recherche
      generale diversifiee (MMR).
    - Sinon : recherche generale MMR.
    """
    categorie = categorie_question(question)

    if categorie == CATEGORIE_ODOO:
        module = module_odoo(question)
        documents = []
        if module in SOURCES_ODOO:
            documents = _rechercher_source(
                question, vectorstore, k, SOURCES_ODOO[module]
            )
        if not documents:
            documents = _rechercher_filtre(
                question, vectorstore, max(k * 3, 24), categorie
            )
            documents = _prioriser_module_odoo(documents, module)
        if documents:
            return _completer_sources(documents[:k], vectorstore)

    if categorie == CATEGORIE_CONVENTION:
        documents_convention = _rechercher_filtre(question, vectorstore, 3, categorie)
        index = _index_lexical(vectorstore)
        if index is not None:
            documents_convention = _dedupliquer(
                documents_convention
                + index.rechercher(
                    question, k=max(k, 8), categorie=CATEGORIE_CONVENTION
                )
            )
        documents_utiles = [
            document
            for document in documents_convention
            if not _est_paratexte_convention(document)
        ]
        documents_convention = (documents_utiles or documents_convention)[:4]
        documents_generaux = _recherche_hybride(
            question, vectorstore, max(k - 3, 1)
        )
        fusion = _dedupliquer(documents_convention + documents_generaux)
        if len(fusion) < k:
            fusion = _dedupliquer(
                fusion + _recherche_hybride(question, vectorstore, k)
            )
        return _completer_sources(fusion[:k], vectorstore)

    return _completer_sources(
        _recherche_hybride(question, vectorstore, k), vectorstore
    )


def construire_historique(
    historique: list[dict[str, Any]] | None,
    max_messages: int = HISTORIQUE_MAX_MESSAGES,
    max_caracteres: int = HISTORIQUE_MAX_CARACTERES,
    langue: str = LANGUE_DEFAUT,
) -> str:
    """Formate les derniers echanges pour comprendre les questions de suivi.

    Seuls les messages les plus recents sont conserves, dans la limite du
    budget de caracteres. L'historique sert a lever les ambiguites, jamais
    de source de faits.
    """
    if not historique:
        return "Aucun."

    roles = ROLES_HISTORIQUE[normaliser_langue(langue)]
    lignes: list[str] = []
    total = 0
    for message in reversed(historique[-max_messages:]):
        contenu = str(message.get("content") or "").strip()
        if not contenu:
            continue
        if len(contenu) > 1000:
            contenu = contenu[:1000] + "..."
        role = roles["user"] if message.get("role") == "user" else roles["assistant"]
        ligne = f"{role} : {contenu}"
        if lignes and total + len(ligne) > max_caracteres:
            break
        lignes.append(ligne)
        total += len(ligne)

    if not lignes:
        return "Aucun."
    return "\n".join(reversed(lignes))


def question_pour_recherche(
    question: str,
    historique: list[dict[str, Any]] | None = None,
) -> str:
    """Enrichit une question de suivi avec la question precedente.

    Une relance courte (« et pour un CDD ? ») n'a pas de sens isolee pour la
    recherche vectorielle : on la rattache a la derniere question de
    l'utilisateur. Le prompt, lui, recoit la question d'origine.
    """
    if not historique:
        return question

    derniere_question = next(
        (
            str(message.get("content") or "").strip()
            for message in reversed(historique)
            if message.get("role") == "user" and str(message.get("content") or "").strip()
        ),
        "",
    )
    if not derniere_question:
        return question

    question = question.strip()
    mots = question.split()
    connecteurs = ("et ", "pour ", "dans ce cas", "meme", "aussi", "alors")
    est_relance = len(mots) <= 8 or question.lower().startswith(connecteurs)
    if not est_relance:
        return question

    return f"{derniere_question} {question}"[:500]


def _est_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")


def nommer_source(metadata: dict[str, Any]) -> str:
    """Nom lisible d'une source : fichier PDF + page, ou URL complete."""
    source = metadata.get("source")
    if not source:
        return "source inconnue"
    source = str(source)
    if _est_url(source):
        return source

    nom = Path(source).name
    prefixe = (
        "Piece jointe : " if metadata.get("origine") == "piece_jointe" else ""
    )
    page_label = metadata.get("page_label")
    if page_label is not None and str(page_label).strip():
        return f"{prefixe}{nom} (p. {page_label})"

    page = metadata.get("page")
    if page is not None:
        try:
            return f"{prefixe}{nom} (p. {int(page) + 1})"
        except (TypeError, ValueError):
            pass
    return f"{prefixe}{nom}"


def extraire_sources(documents: list[Any]) -> list[dict[str, Any]]:
    """Liste dedupliquee des sources, dans l'ordre de pertinence."""
    sources: dict[tuple[str, str], dict[str, Any]] = {}
    for document in documents:
        metadata = getattr(document, "metadata", None) or {}
        source = str(metadata.get("source") or "")
        page = metadata.get("page")
        cle = (source, str(page))
        if cle not in sources:
            if metadata.get("origine") == "piece_jointe":
                type_source = "piece_jointe"
            else:
                type_source = "web" if _est_url(source) else "pdf"
            sources[cle] = {
                "nom": nommer_source(metadata),
                "type": type_source,
                "source": source,
                "page": page,
                "extraits": [],
            }
        sources[cle]["extraits"].append(document.page_content)
    return list(sources.values())


def construire_contexte(documents: list[Any]) -> str:
    """Contexte numerote [1]...[n] avec le nom de chaque source."""
    blocs = []
    for numero, document in enumerate(documents, start=1):
        metadata = getattr(document, "metadata", None) or {}
        blocs.append(f"[{numero}] Source : {nommer_source(metadata)}\n{document.page_content}")
    return "\n\n".join(blocs)


def construire_prompt(
    question: str,
    documents: list[Any],
    historique: list[dict[str, Any]] | None = None,
    langue: str = LANGUE_DEFAUT,
) -> str:
    """Prompt final : consignes, historique, contexte numerote et question.

    Le modele suit la langue dominante des instructions : le prompt complet
    est donc redige dans la langue demandee, et pas seulement la consigne.
    """
    code = normaliser_langue(langue)
    return PROMPTS_PAR_LANGUE[code].format(
        consigne_langue=LANGUES[code]["consigne"],
        historique=construire_historique(historique, langue=code),
        contexte=construire_contexte(documents),
        question=question,
    )


def repondre(
    question: str,
    vectorstore: Any | None,
    llm: Any,
    k: int = TOP_K,
    pieces_jointes: Any | None = None,
    historique: list[dict[str, Any]] | None = None,
    langue: str = LANGUE_DEFAUT,
) -> dict[str, Any]:
    """Recherche le contexte, interroge le LLM et retourne reponse + sources.

    ``langue`` est le code de la langue de la reponse ("fr", "en" ou "ko") ;
    toute valeur inconnue retombe sur le francais.

    Des qu'une piece jointe est disponible, elle constitue la seule source de
    contexte : la base vectorielle n'est pas interrogee, afin que le contenu
    envoye par l'utilisateur ne soit pas melange avec les PDF de DRH.
    La base vectorielle n'est utilisee qu'en l'absence de piece jointe.

    Si les pieces jointes tiennent sous ``MAX_CARACTERES_CONTEXTE_COMPLET``,
    leur texte entier est transmis au LLM (utile pour un bulletin de paie
    court) ; sinon, seuls les k extraits les plus proches sont retenus.

    ``historique`` contient les echanges precedents : il sert a comprendre
    les questions de suivi et a enrichir la requete de recherche, sans
    jamais constituer une source de faits.
    """
    question_recherche = question_pour_recherche(question, historique)
    documents: list[Any] = []
    if pieces_jointes is not None:
        documents = pieces_jointes.documents_complets()
        if documents is None:
            documents = list(pieces_jointes.rechercher(question_recherche, k=k))
    if not documents and vectorstore is not None:
        documents = rechercher(question_recherche, vectorstore, k=k)
    if not documents:
        return {
            "reponse": MESSAGES_SANS_RESULTAT[normaliser_langue(langue)],
            "sources": [],
        }

    prompt = construire_prompt(question, documents, historique=historique, langue=langue)
    message = llm.invoke(prompt)
    contenu = getattr(message, "content", None)
    if contenu is None:
        contenu = str(message)
    return {"reponse": contenu, "sources": extraire_sources(documents)}


def _base_disponible() -> bool:
    return Path(CHROMA_DIR, "chroma.sqlite3").is_file()


def infos_ingestion(chroma_dir: str | Path = CHROMA_DIR) -> dict[str, Any]:
    """Date et taille de la derniere ingestion de la base documentaire.

    Le manifeste ecrit par ``ingest.py`` fait foi ; pour une base plus
    ancienne qui n'en possede pas, la date de modification de
    ``chroma.sqlite3`` sert de repli. Retourne ``{}`` si la base est absente.
    """
    dossier = Path(chroma_dir)
    manifeste = dossier / MANIFESTE_INGESTION
    if manifeste.is_file():
        try:
            contenu = json.loads(manifeste.read_text(encoding="utf-8"))
            date = datetime.fromisoformat(str(contenu["date_ingestion"]))
            chunks = contenu.get("chunks")
        except (OSError, ValueError, KeyError, TypeError):
            logger.warning("Manifeste d'ingestion illisible : %s", manifeste)
        else:
            return {
                "date": date,
                "chunks": chunks if isinstance(chunks, int) else None,
            }

    base = dossier / "chroma.sqlite3"
    if base.is_file():
        return {
            "date": datetime.fromtimestamp(base.stat().st_mtime),
            "chunks": None,
        }
    return {}


def texte_a_propos(
    infos: dict[str, Any] | None = None,
    version: str = APP_VERSION,
) -> str:
    """Contenu Markdown de la fenetre « A propos » du menu Streamlit."""
    infos = infos or {}
    date = infos.get("date")
    if date is None:
        ingestion = "Ingestion des données : inconnue"
    else:
        ingestion = f"Ingestion des données : {date:%d/%m/%Y à %H:%M}"
        chunks = infos.get("chunks")
        if isinstance(chunks, int):
            ingestion += f" ({chunks:,} extraits)".replace(",", " ")

    return "\n".join(
        [
            "**Assistant DRH – IA**",
            "",
            f"- Version : `{version}`",
            f"- {ingestion}",
            f"- Modèle de langage : `{LLM_MODEL}`",
            f"- Embeddings : `{EMBEDDING_MODEL}`",
            "",
            "Réponses générées localement à partir de la base documentaire RH.",
        ]
    )


def cite_des_sources(texte: str) -> bool:
    """Indique si la reponse cite au moins une source numerotee ([1], [2]...)."""
    return bool(re.search(r"\[\d+\]", texte or ""))


def resume_raisonnement(
    sources: list[dict[str, Any]], reponse: str = ""
) -> str:
    """Resume synthetique : d'ou vient la reponse et comment elle a ete construite."""
    if not sources:
        return ""

    nb_extraits = sum(len(source.get("extraits") or []) for source in sources)
    types = Counter(str(source.get("type") or "") for source in sources)
    origines = []
    if types.get("pdf"):
        origines.append("base documentaire RH")
    if types.get("web"):
        origines.append("sources web")
    if types.get("piece_jointe"):
        origines.append("pieces jointes")
    origine = ", ".join(origines) if origines else "sources diverses"

    lignes = [
        "**Raisonnement**",
        (
            f"- Reponse fondee sur {nb_extraits} extraits issus de "
            f"{len(sources)} sources ({origine})."
        ),
        (
            "- Extraits classes par pertinence puis numerotes [1]...[n] dans "
            "le contexte transmis au modele : les numeros cites dans la "
            "reponse renvoient a la liste ci-dessous."
        ),
    ]
    if reponse and not cite_des_sources(reponse):
        lignes.append(
            "- ⚠️ La reponse ne cite pas ses sources : verifiez les extraits "
            "ci-dessous avant de l'utiliser."
        )

    lignes.extend(["", "**Sources**"])
    for numero, source in enumerate(sources, start=1):
        nombre = len(source.get("extraits") or [])
        lignes.append(f"[{numero}] {source['nom']} — {nombre} extrait(s)")
    return "\n".join(lignes)


def _afficher_sources(
    st: Any,
    sources: list[dict[str, Any]],
    avertissement: str | None = None,
    reponse: str = "",
) -> None:
    """Regroupe raisonnement, sources et extraits dans un volet replie."""
    if not sources:
        return
    with st.expander("Détails"):
        if avertissement:
            st.caption(avertissement)
        st.markdown(resume_raisonnement(sources, reponse))
        st.divider()
        st.markdown("**Extraits utilisés**")
        for source in sources:
            st.markdown(f"**{source['nom']}**")
            for extrait in source["extraits"]:
                texte = extrait if len(extrait) <= 600 else extrait[:600] + "..."
                st.caption(texte)


def _initialiser_session(st: Any) -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "langue" not in st.session_state:
        st.session_state.langue = LANGUE_DEFAUT
    if "pieces_jointes" not in st.session_state:
        st.session_state.pieces_jointes = IndexPiecesJointes(creer_embeddings())


def _style(st: Any) -> None:
    st.markdown(
        """
        <style>
        .block-container { max-width: 820px; padding-top: 2.5rem; }
        h1 { font-weight: 700; letter-spacing: -0.02em; }
        [data-testid="stChatMessage"] { padding: 0.4rem 0; }

        /* Animation de chargement : points de suspension qui clignotent. */
        [data-testid="stSpinnerIcon"] { display: none; }
        [data-testid="stSpinner"]::before {
            content: "...";
            font-size: 1.1rem;
            line-height: 1;
            letter-spacing: 0.1em;
            margin-right: 0.35rem;
            animation: points-clignotants 1.1s ease-in-out infinite;
        }
        @keyframes points-clignotants {
            0%, 100% { opacity: 0.35; }
            50% { opacity: 1; }
        }
        /* Masque l'icone animee du statut de chargement en haut a droite. */
        [data-testid="stStatusWidgetRunningIcon"] { display: none; }

        /* Retire l'option "Record screen" du menu Streamlit. */
        [data-testid="stMainMenuItem-recordScreencast"] { display: none !important; }
        @media (prefers-reduced-motion: reduce) {
            [data-testid="stSpinner"]::before { animation: none; opacity: 1; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    """Point d'entree de l'application Streamlit (compatibilité)."""
    # Délégation au portail en ciblant la vue RH quand possible.
    try:
        import os
        import app_portail

        os.environ.setdefault("PORTAIL_VUE", "rh")
        app_portail.main()
    except Exception:
        # Repli minimal : exécution historique si portail indisponible.
        import streamlit as st

        st.set_page_config(
            page_title="RH - IA",
            page_icon="briefcase",
            layout="centered",
            menu_items={"About": texte_a_propos(infos_ingestion())},
        )
        _style(st)
        _initialiser_session(st)
        st.title("RH - IA")
        st.caption(
            "Posez vos questions RH (droit du travail, convention collective de la "
            "restauration rapide, contrats, paie, absences, Odoo...) : les reponses "
            "sont fondees sur les documents indexes, avec leurs sources."
        )
        st.caption(
            "⚠️ Reponse generee automatiquement : verifiez toujours les sources "
            "affichees avant toute decision juridique ou disciplinaire."
        )

        index_pj = st.session_state.pieces_jointes

        with st.sidebar:
            st.header("Configuration")
            st.selectbox(
                "Langue de la réponse",
                options=list(LANGUES),
                format_func=lambda code: LANGUES[code]["nom"],
                key="langue",
                help="S'applique aux prochaines réponses ; l'interface reste en français.",
            )
            st.caption(f"Modele de langage : `{LLM_MODEL}`")
            st.caption(f"Embeddings : `{EMBEDDING_MODEL}`")
            st.caption(f"Extraits par question : {TOP_K} (recherche diversifiee)")
            st.divider()

            st.subheader("Pieces jointes")
            noms_pj = index_pj.noms()
            if not noms_pj:
                st.caption("Aucun fichier joint (PDF, TXT, Markdown).")
            else:
                for nom in noms_pj:
                    colonne_nom, colonne_action = st.columns([5, 1])
                    with colonne_nom:
                        st.caption(f"📎 {nom}")
                    with colonne_action:
                        if st.button(
                            "✕",
                            key=f"retirer_piece_jointe_{nom}",
                            help=f"Retirer {nom}",
                        ):
                            index_pj.retirer(nom)
                            st.rerun()
                if st.button("Tout retirer", use_container_width=True):
                    for nom in list(index_pj.noms()):
                        index_pj.retirer(nom)
                    st.rerun()
            if not _base_disponible():
                st.warning(
                    "Base RH introuvable (chroma_db/rh) : seules les pieces jointes seront utilisees. "
                    "Lancez l'ingestion du module RH (python ingest.py --module rh)."
                )

            st.divider()
            if st.button("Effacer la conversation", use_container_width=True):
                st.session_state.messages = []
                st.rerun()

        @st.cache_resource(show_spinner=False)
        def _vectorstore() -> Any:
            return creer_vectorstore()

        @st.cache_resource(show_spinner=False)
        def _llm() -> Any:
            return creer_llm()

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if message.get("fichiers"):
                    st.caption(
                        "Pieces jointes : " + ", ".join(message["fichiers"])
                    )
                if message["role"] == "assistant":
                    _afficher_sources(
                        st,
                        message.get("sources", []),
                        reponse=message.get("content", ""),
                    )

        saisie = st.chat_input(
            "Posez votre question RH...",
            accept_file="multiple",
            file_type=["pdf", "txt", "md"],
            max_upload_size=20,
        )
        if saisie is None:
            return

        question = (getattr(saisie, "text", "") or "").strip()
        fichiers = list(getattr(saisie, "files", None) or [])
        if not question and not fichiers:
            return

        noms_joints = []
        for fichier in fichiers:
            try:
                with st.spinner(f"Lecture de {fichier.name}..."):
                    index_pj.ajouter(fichier.name, fichier.getvalue())
                noms_joints.append(fichier.name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Piece jointe ignoree (%s) : %s", fichier.name, exc)
                st.warning(f"Impossible d'ajouter {fichier.name} : {exc}")

        if not question:
            if not noms_joints:
                return
            question = "Resume le(s) document(s) joint(s)."

        historique = list(st.session_state.messages[-HISTORIQUE_MAX_MESSAGES:])
        message_utilisateur = {"role": "user", "content": question}
        if noms_joints:
            message_utilisateur["fichiers"] = noms_joints
        st.session_state.messages.append(message_utilisateur)
        with st.chat_message("user"):
            st.markdown(question)
            if noms_joints:
                st.caption("Pieces jointes : " + ", ".join(noms_joints))

        with st.chat_message("assistant"):
            base_disponible = _base_disponible()
            if not base_disponible and index_pj.est_vide():
                st.error(
                    "Base RH introuvable dans ./chroma_db/rh et aucun fichier "
                    "joint. Lancez d'abord l'ingestion du module RH : python ingest.py --module rh"
                )
                return
            utilise_pieces_jointes = not index_pj.est_vide()
            try:
                vectorstore = (
                    _vectorstore()
                    if base_disponible and not utilise_pieces_jointes
                    else None
                )
                if utilise_pieces_jointes:
                    st.caption(
                        "Reponse fondee uniquement sur les pieces jointes, sans "
                        "melange avec la base RH."
                    )
                    texte_spinner = "Analyse des pieces jointes..."
                else:
                    texte_spinner = "Recherche dans la base RH..."
                with st.spinner(texte_spinner):
                    resultat = repondre(
                        question,
                        vectorstore,
                        _llm(),
                        pieces_jointes=index_pj,
                        historique=historique,
                        langue=st.session_state.langue,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Echec de la generation")
                st.error(
                    "Impossible d'interroger la base RH ou les pieces jointes. "
                    f"Verifiez qu'Ollama est demarre sur {OLLAMA_BASE_URL}.\n\n"
                    f"Detail : {exc}"
                )
                return

            st.markdown(resultat["reponse"])
            _afficher_sources(
                st, resultat["sources"], reponse=resultat["reponse"]
            )
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": resultat["reponse"],
                    "sources": resultat["sources"],
                }
            )
