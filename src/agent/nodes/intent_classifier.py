"""BERT-based intent classifier using BGE-small-zh-v1.5 embeddings.

Reuses the shared SentenceTransformer singleton from embedder.py (zero extra memory).
Classifies user messages by cosine similarity to pre-computed prototype vectors.
"""

import asyncio

import numpy as np

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)
from src.agent.state import IntentType

# Temperature for softmax confidence calibration (lower = sharper distribution)
_TEMPERATURE = 0.15

# ── Prototype example sentences per intent ──────────────────────────────────
# SLOT_FILLING is excluded — it is always caught by the regex layer before
# reaching the BERT classifier.
_INTENT_EXAMPLES: dict[IntentType, list[str]] = {
    IntentType.PRODUCT_INQUIRY: [
        "这款衣服是什么材质的",
        "这个产品有哪些规格和尺寸",
        "有没有其他颜色可以选",
        "这个尺码表准不准，我该选哪个号",
    ],
    IntentType.PRICING_INQUIRY: [
        "这个多少钱",
        "现在有什么优惠活动吗",
        "有优惠券可以用吗",
        "买两件有没有折扣",
    ],
    IntentType.STOCK_CHECK: [
        "这款有现货吗",
        "什么时候能补货",
        "这个颜色L码还有库存吗",
        "缺货的商品什么时候上架",
    ],
    IntentType.ORDER_STATUS: [
        "我的订单现在什么状态",
        "下单后多久能发货",
        "帮我查一下订单进度",
        "订单显示已发货但怎么一直没有物流更新",
    ],
    IntentType.LOGISTICS_QUERY: [
        "快递到哪了",
        "物流信息怎么不更新了",
        "为什么三天了还没收到货",
        "快递单号查不到物流信息",
    ],
    IntentType.MODIFY_ORDER: [
        "我要修改订单的收货地址",
        "帮我改一下收货人电话号码",
        "订单里再加一件商品",
        "把这个订单取消了我重新下单",
    ],
    IntentType.RETURN_REQUEST: [
        "我要退货",
        "质量不好想退掉这个商品",
        "买错了想申请退货",
        "不想要了怎么退货退款",
    ],
    IntentType.EXCHANGE_REQUEST: [
        "想换个尺码",
        "颜色不喜欢可以换吗",
        "换同款的其他颜色可以吗",
        "收到的商品是坏的换一个新的",
    ],
    IntentType.REFUND_INQUIRY: [
        "退款什么时候能到账",
        "退货后多久能收到退款",
        "退款申请审核通过了吗",
        "退款的金额怎么不对",
    ],
    IntentType.COMPLAINT: [
        "我要投诉你们平台",
        "你们的服务太差了",
        "客服态度特别恶劣我要举报",
        "我要找你们领导反映问题",
    ],
    IntentType.TECHNICAL_ISSUE: [
        "App打不开了",
        "页面一直在加载中转圈",
        "提交订单的时候报错了",
        "支付页面白屏点不了",
    ],
    IntentType.ACCOUNT_ISSUE: [
        "忘记密码了怎么找回",
        "注册时收不到短信验证码",
        "账号被冻结了怎么办",
        "实名认证一直通不过",
    ],
    IntentType.GENERAL_INQUIRY: [
        "你好在吗",
        "我想咨询一下问题",
        "能帮我看看这个是咋回事吗",
        "有个问题想问客服",
    ],
    IntentType.HUMAN_HANDOFF: [
        "转人工客服",
        "找你们经理过来",
        "不想和机器人说话",
        "能不能叫一个真人客服来",
    ],
}


class IntentClassifier:
    """BERT-based intent classifier reusing the BGE-small-zh-v1.5 model.

    Singleton — use IntentClassifier.get_instance() to obtain the shared instance.
    Prototype vectors are computed lazily on first use.
    """

    _instance: "IntentClassifier | None" = None

    def __init__(self):
        self._model = None       # SentenceTransformer, set by _get_model()
        self._prototypes = None  # np.ndarray of shape (N, 512), L2-normalized
        self._labels = None      # list[IntentType], parallel to prototypes

    @classmethod
    def get_instance(cls) -> "IntentClassifier":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_model(self):
        """Lazy-load the shared SentenceTransformer singleton from embedder.py."""
        if self._model is None:
            from src.rag.ingestion.embedder import get_embedding_model
            self._model = get_embedding_model()
        return self._model

    def _build_prototypes(self) -> None:
        """Encode all example sentences and compute per-intent prototype vectors."""
        model = self._get_model()
        labels: list[IntentType] = []
        all_sentences: list[str] = []
        intent_sizes: list[int] = []

        for intent, examples in _INTENT_EXAMPLES.items():
            labels.append(intent)
            intent_sizes.append(len(examples))
            all_sentences.extend(examples)

        embeddings = model.encode(all_sentences, normalize_embeddings=True, show_progress_bar=False)

        # Average embeddings within each intent → prototype vector
        dim = embeddings.shape[1]
        prototypes = np.zeros((len(labels), dim), dtype=np.float32)
        offset = 0
        for i, size in enumerate(intent_sizes):
            prototypes[i] = embeddings[offset:offset + size].mean(axis=0)
            offset += size

        # Re-normalize after averaging
        prototypes /= np.linalg.norm(prototypes, axis=1, keepdims=True)

        self._labels = labels
        self._prototypes = prototypes
        logger.info("intent_prototypes_built", intent_count=len(labels))

    async def classify(self, text: str) -> tuple[IntentType, float]:
        """Classify user text into an intent with confidence score.

        Returns (intent, confidence) where confidence is softmax probability.
        If below threshold, the caller should fall back to GENERAL_INQUIRY.
        """
        if self._prototypes is None:
            await asyncio.to_thread(self._build_prototypes)

        model = self._get_model()
        query_vec = await asyncio.to_thread(
            model.encode, [text], normalize_embeddings=True, show_progress_bar=False,
        )
        query_vec = np.asarray(query_vec[0], dtype=np.float32)

        # Cosine similarity (dot product since vectors are normalized)
        similarities = np.dot(self._prototypes, query_vec)

        # Softmax with temperature
        exp_sims = np.exp(similarities / _TEMPERATURE)
        probs = exp_sims / exp_sims.sum()

        best_idx = int(np.argmax(probs))
        return self._labels[best_idx], float(probs[best_idx])

    async def classify_top_k(self, text: str, k: int = 3) -> list[tuple[IntentType, float]]:
        """Return top-k intents with confidence scores (for diagnostics)."""
        if self._prototypes is None:
            await asyncio.to_thread(self._build_prototypes)

        model = self._get_model()
        query_vec = await asyncio.to_thread(
            model.encode, [text], normalize_embeddings=True, show_progress_bar=False,
        )
        query_vec = np.asarray(query_vec[0], dtype=np.float32)

        similarities = np.dot(self._prototypes, query_vec)
        exp_sims = np.exp(similarities / _TEMPERATURE)
        probs = exp_sims / exp_sims.sum()

        top_indices = np.argsort(probs)[::-1][:k]
        return [(self._labels[i], float(probs[i])) for i in top_indices]
