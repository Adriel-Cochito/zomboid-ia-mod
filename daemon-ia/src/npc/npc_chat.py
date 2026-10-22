"""
Interpretação de ordens digitadas pelo jogador (determinística, sem LLM).
A LLM só responde a conversa livre; ordens viram modo por palavra-chave.
"""
import re
import unicodedata


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


# Ordem importa: a primeira que casar vence.
_PATTERNS = [
    ("defender", r"\b(defende|defenda|protege|proteja|cobre|cubra|ataca|ataque|mata)\b"),
    ("saquear",  r"\b(pega|pegue|saqueia|saqueie|loota|procura|procure|busca|busque)\b"),
    ("ficar",    r"\b(fica|fique|espera|espere|aguarda|aguarde|para ai|nao saia)\b"),
    ("seguir",   r"\b(segue|siga|vem|venha|comigo|acompanha|acompanhe)\b"),
]


def detect_mode(text: str):
    """Devolve 'seguir' | 'ficar' | 'defender' | 'saquear' ou None."""
    norm = _normalize(text or "")
    for mode, pattern in _PATTERNS:
        if re.search(pattern, norm):
            return mode
    return None


# --- Pedidos de busca ("procura combustível", "consegue lotear algo?") -> comando fetch ---
_FETCH_VERBS = (r"\b(pega|pegue|pegar|procura|procure|procurar|busca|busque|buscar|acha|ache|achar|"
                r"encontra|encontre|encontrar|traz|traga|trazer|junta|junte|coleta|colete|"
                r"vasculha|vasculhe|vasculhar|explora|explore|olha|olhe)\b")
# palavras que, sozinhas, já significam "vá lootear"
_FETCH_ANYTIME = r"\b(lotear|lootear|lootar|loot|lota|loota|saquear|saqueia|saqueie|saque)\b"

# (rótulo para falar, palavras-chave para o adapter; "-x" exclui; "cat:X" = categoria do item)
_FETCH_TOPICS = [
    (r"\b(combustivel|gasolina|gas|galao|petroleo|diesel)\b", ("combustível", "petrol,-empty")),
    (r"\b(comida|comer|alimento|alimentos|lata|latas|enlatado|enlatados|rango|mantimento|mantimentos)\b", ("comida", "cat:Food")),
    (r"\b(agua|bebida|beber)\b",                               ("água", "water,cat:Food")),
    (r"\b(remedio|remedios|curativo|bandagem|atadura|medicamento|medicamentos)\b", ("remédios", "cat:FirstAid")),
    (r"\b(municao|bala|balas|cartucho|cartuchos)\b",           ("munição", "ammo,bullet,shell,round")),
    (r"\b(arma|armas|faca|machado|taco)\b",                    ("armas", "cat:Weapon")),
    (r"\b(ferramenta|ferramentas|martelo|chave)\b",            ("ferramentas", "cat:Tool")),
    (r"\b(livro|livros|revista|revistas|manual|manuais)\b",     ("livros", "cat:Literature,book,mag")),
    (r"\b(suprimento|suprimentos|coisa util|coisas uteis|material|materiais|recursos|itens|item|tralha|tralhas|coisas)\b",
     ("coisas úteis", "@util")),
]


def detect_fetch(text: str):
    """Devolve (rotulo, palavras_chave) se o jogador pediu para buscar/lootear algo; senão None.
    Dispara com (verbo de busca + tema) ou com uma palavra de loot ("lotear"). Vários temas se somam."""
    norm = _normalize(text or "")
    has_verb = re.search(_FETCH_VERBS, norm) is not None
    anytime = re.search(_FETCH_ANYTIME, norm) is not None
    if not (has_verb or anytime):
        return None
    labels, kws = [], []
    for pattern, (label, kw) in _FETCH_TOPICS:
        if re.search(pattern, norm):
            labels.append(label)
            kws.append(kw)
    if not labels:
        if anytime:
            return "coisas úteis", "@util"
        return None
    return " e ".join(labels[:3]), ",".join(kws)