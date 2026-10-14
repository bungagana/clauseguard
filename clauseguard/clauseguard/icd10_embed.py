"""Dense retrieval support for the ICD-10 coder: embedding backends, an on-disk category index, rank fusion.

Two interchangeable backends embed the ~1.9k three-character category descriptions once; the
vectors are cached under data/cache/ keyed by backend, model name and a hash of the exact texts.
Nothing here is required at runtime: a missing cache, a missing model file, a missing optional
package or an unreachable API all surface as `EmbeddingUnavailable`, and the coder then retrieves
with BM25 alone.

  gemini   Gemini embeddings API through the llm.py key pool (RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY)
  e5onnx   multilingual-e5-small, int8 ONNX export, CPU, onnxruntime + tokenizers (no PyTorch)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Protocol, Sequence

import numpy as np

from . import config, llm

log = logging.getLogger("clauseguard.icd10_embed")

RRF_K = 60
GEMINI_MODEL = os.getenv("CG_ICD_EMBED_MODEL", "gemini-embedding-2")
GEMINI_DIM = 768
E5_DIR = config.CACHE_DIR / "models" / "multilingual-e5-small"
E5_MODEL_FILE = "model_int8.onnx"
E5_TOKENIZER_FILE = "tokenizer.json"
E5_NAME = "multilingual-e5-small-int8"
MAX_MEMBER_DESCRIPTIONS = 6
BACKENDS = ("gemini", "e5onnx")


class EmbeddingUnavailable(RuntimeError):
    """No embedding vectors can be produced (not an error for the pipeline: BM25 only)."""


class Backend(Protocol):
    name: str
    model: str

    def embed(self, texts: Sequence[str], kind: str) -> np.ndarray:
        """Rows are L2-normalised float32 vectors; kind is 'document' or 'query'."""


def _normalise_rows(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    n = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.maximum(n, 1e-12)


# --------------------------------------------------------------------------- gemini
class GeminiBackend:
    """Gemini embeddings API. gemini-embedding-2 returns ONE vector for a list of strings, so it is called
    once per text (8 in parallel); gemini-embedding-001 accepts a batch of texts per call."""

    name = "gemini"

    def __init__(self, model: str = GEMINI_MODEL, batch: int = 32, workers: int = 8) -> None:
        self.model, self.batch, self.workers = model, batch, workers

    def _call(self, contents, task: str) -> list[list[float]]:
        from google.genai import types as gt

        delay = 3.0
        for attempt in range(10):
            try:
                resp = llm.client().models.embed_content(
                    model=self.model, contents=contents,
                    config=gt.EmbedContentConfig(task_type=task, output_dimensionality=GEMINI_DIM))
                EMBED_STATS["api_calls"] += 1
                return [list(e.values) for e in resp.embeddings]
            except RuntimeError as e:
                raise EmbeddingUnavailable(str(e)[:120]) from e
            except Exception as e:  # noqa: BLE001 - google client raises many types
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    if "per_day" in msg.lower() or "PerDay" in msg:
                        raise EmbeddingUnavailable("daily embedding quota exhausted: " + msg[:100]) from e
                    llm.rotate_key()
                    time.sleep(20)
                    continue
                if attempt >= 9:
                    raise EmbeddingUnavailable(msg[:120]) from e
                time.sleep(delay)
                delay = min(delay * 2, 30)
        raise EmbeddingUnavailable("embedding retries exhausted")

    def embed(self, texts: Sequence[str], kind: str) -> np.ndarray:
        if os.getenv("CG_OFFLINE") == "1" or llm.REPLAY_ONLY:
            raise EmbeddingUnavailable("embedding API disabled (CG_OFFLINE / replay-only)")
        task = "RETRIEVAL_DOCUMENT" if kind == "document" else "RETRIEVAL_QUERY"
        if self.model.endswith("embedding-001"):
            out: list[list[float]] = []
            for start in range(0, len(texts), self.batch):
                out.extend(self._call(list(texts[start:start + self.batch]), task))
        else:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(min(self.workers, max(1, len(texts)))) as ex:
                out = [r[0] for r in ex.map(lambda t: self._call(t, task), texts)]
        return _normalise_rows(np.array(out))


# --------------------------------------------------------------------------- local e5 (onnx)
class E5OnnxBackend:
    name = "e5onnx"
    model = E5_NAME

    def __init__(self, directory: Path = E5_DIR) -> None:
        self.dir = directory
        self._session = None
        self._tok = None

    def available(self) -> bool:
        return (self.dir / E5_MODEL_FILE).exists() and (self.dir / E5_TOKENIZER_FILE).exists()

    def _load(self) -> None:
        if self._session is not None:
            return
        if not self.available():
            raise EmbeddingUnavailable(f"e5 ONNX files missing in {self.dir} (run scripts/fetch_real_data.py --only e5onnx)")
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as e:
            raise EmbeddingUnavailable(f"optional package missing: {e.name}") from e
        try:
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = max(1, min(4, os.cpu_count() or 1))
            self._session = ort.InferenceSession(str(self.dir / E5_MODEL_FILE), opts, providers=["CPUExecutionProvider"])
            tok = Tokenizer.from_file(str(self.dir / E5_TOKENIZER_FILE))
            tok.enable_truncation(max_length=256)
            tok.enable_padding(pad_id=1, pad_token="<pad>")
            self._tok = tok
        except Exception as e:  # noqa: BLE001
            self._session = None
            raise EmbeddingUnavailable(f"e5 ONNX could not be loaded: {str(e)[:120]}") from e

    def embed(self, texts: Sequence[str], kind: str) -> np.ndarray:
        self._load()
        prefix = "passage: " if kind == "document" else "query: "
        rows = []
        names = {i.name for i in self._session.get_inputs()}
        for start in range(0, len(texts), 32):
            enc = self._tok.encode_batch([prefix + t for t in texts[start:start + 32]])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in names:
                feed["token_type_ids"] = np.zeros_like(ids)
            hidden = self._session.run(None, feed)[0]
            m = mask[:, :, None].astype(np.float32)
            rows.append((hidden * m).sum(axis=1) / np.maximum(m.sum(axis=1), 1.0))
        return _normalise_rows(np.concatenate(rows))


EMBED_STATS = {"api_calls": 0}
_BACKENDS: dict[str, Backend] = {}


def get_backend(name: str) -> Backend:
    if name not in BACKENDS:
        raise EmbeddingUnavailable(f"unknown embedding backend {name!r}")
    if name not in _BACKENDS:
        _BACKENDS[name] = GeminiBackend() if name == "gemini" else E5OnnxBackend()
    return _BACKENDS[name]


def set_backend(name: str, backend: Optional[Backend]) -> None:
    """Install (or, with None, remove) a backend object; used by tests and the evaluation script."""
    if backend is None:
        _BACKENDS.pop(name, None)
    else:
        _BACKENDS[name] = backend


# --------------------------------------------------------------------------- category documents + index cache
def category_documents(codes: dict[str, str], labels: dict[str, str]) -> dict[str, str]:
    """Text embedded for each category: the official category label plus distinct member-code descriptions."""
    members: dict[str, list[str]] = {}
    for code, desc in codes.items():
        members.setdefault(code[:3], []).append(desc)
    docs = {}
    for cat in sorted(labels):
        label = labels[cat]
        seen = {label.lower()}
        extra = []
        for d in members.get(cat, []):
            if d.lower() not in seen:
                seen.add(d.lower())
                extra.append(d)
            if len(extra) >= MAX_MEMBER_DESCRIPTIONS:
                break
        docs[cat] = (label + (". " + "; ".join(extra) if extra else ""))[:500]
    return docs


def docs_digest(docs: dict[str, str]) -> str:
    h = hashlib.sha256()
    for k in sorted(docs):
        h.update(k.encode())
        h.update(b"\x00")
        h.update(docs[k].encode())
        h.update(b"\x01")
    return h.hexdigest()


def index_path(backend: Backend, docs: dict[str, str]) -> Path:
    safe = "".join(c if c.isalnum() or c in "-." else "_" for c in backend.model)
    return config.CACHE_DIR / f"icd_emb_{backend.name}_{safe}_{docs_digest(docs)[:16]}.npz"


class CategoryIndex:
    def __init__(self, ids: list[str], matrix: np.ndarray) -> None:
        self.ids, self.matrix = ids, matrix

    def rank(self, query_vec: np.ndarray, k: int) -> list[tuple[str, float]]:
        sims = self.matrix @ np.asarray(query_vec, dtype=np.float32)
        order = np.argsort(-sims, kind="stable")[:k]
        return [(self.ids[i], float(sims[i])) for i in order]


def load_index(backend: Backend, docs: dict[str, str]) -> Optional[CategoryIndex]:
    """Cached index for exactly these texts and this model, or None (never builds, never raises)."""
    path = index_path(backend, docs)
    try:
        if not path.exists():
            return None
        with np.load(path, allow_pickle=False) as z:
            ids = [str(x) for x in z["ids"]]
            matrix = z["matrix"].astype(np.float32)
        if ids != sorted(docs) or matrix.shape[0] != len(ids):
            return None
        return CategoryIndex(ids, matrix)
    except Exception as e:  # noqa: BLE001 - a corrupt cache is a miss
        log.warning("embedding cache unreadable (%s): %s", path.name, str(e)[:80])
        return None


def build_index(backend: Backend, docs: dict[str, str], force: bool = False) -> CategoryIndex:
    """Embed every category document once and cache the vectors. Raises EmbeddingUnavailable."""
    if not force:
        hit = load_index(backend, docs)
        if hit is not None:
            return hit
    ids = sorted(docs)
    matrix = query_vectors(backend, [docs[i] for i in ids], "document", chunk=backend_batch(backend))
    path = index_path(backend, docs)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, ids=np.array(ids), matrix=matrix.astype(np.float32))
    os.replace(tmp, path)
    return CategoryIndex(ids, matrix.astype(np.float32))


# --------------------------------------------------------------------------- query vectors (cached on disk)
QUERY_CACHE_ENABLED = True


def backend_batch(backend: Backend) -> int:
    return int(getattr(backend, "batch", 32))


def query_vectors(backend: Backend, texts: Sequence[str], kind: str = "query", chunk: int = 0) -> np.ndarray:
    """Vectors for texts, read from and written to a per-text disk cache; embeds only the misses.

    Chunked so an interrupted or quota-limited document build keeps what it already paid for.
    """
    prefix = "icdq_" if kind == "query" else "icdd_"
    paths = [config.CACHE_DIR / (prefix + hashlib.sha256(f"{backend.name}|{backend.model}|{t}".encode()).hexdigest() + ".json") for t in texts]
    vecs: list[Optional[np.ndarray]] = [None] * len(texts)
    missing = []
    for i, p in enumerate(paths):
        if QUERY_CACHE_ENABLED and p.exists():
            try:
                vecs[i] = np.array(json.loads(p.read_text(encoding="utf8")), dtype=np.float32)
                continue
            except Exception:  # noqa: BLE001
                pass
        missing.append(i)
    step = chunk or len(missing) or 1
    for start in range(0, len(missing), step):
        idx = missing[start:start + step]
        got = backend.embed([texts[i] for i in idx], kind)
        for j, i in enumerate(idx):
            vecs[i] = got[j]
            if QUERY_CACHE_ENABLED:
                try:
                    paths[i].write_text(json.dumps([round(float(x), 6) for x in got[j]]), encoding="utf8")
                except OSError:
                    pass
    return np.stack(vecs)


# --------------------------------------------------------------------------- fusion
def rrf(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal rank fusion: score(d) = sum over rankings of 1 / (k + rank), rank starting at 1."""
    score: dict[str, float] = {}
    for ranking in rankings:
        for pos, doc in enumerate(ranking, start=1):
            score[doc] = score.get(doc, 0.0) + 1.0 / (k + pos)
    return sorted(score.items(), key=lambda x: (-x[1], x[0]))
