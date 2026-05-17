"""Tests for intent classification."""
import numpy as np
import pytest
from unittest.mock import MagicMock

from src.agent.nodes.intent import _fast_intent_classify
from src.agent.state import IntentType


class TestFastIntentClassify:
    def test_return_intent(self):
        intent, confidence = _fast_intent_classify("我想退货，怎么操作？")
        assert intent == IntentType.RETURN_REQUEST

    def test_complaint_intent(self):
        intent, confidence = _fast_intent_classify("我要投诉你们客服态度太差了")
        assert intent == IntentType.COMPLAINT

    def test_order_status(self):
        intent, confidence = _fast_intent_classify("帮我查一下订单到哪里了")
        assert intent == IntentType.ORDER_STATUS

    def test_logistics(self):
        intent, confidence = _fast_intent_classify("我的快递到哪了3天没更新了")
        assert intent == IntentType.LOGISTICS_QUERY

    def test_product_inquiry(self):
        intent, confidence = _fast_intent_classify("这款有没有现货")
        assert intent == IntentType.PRODUCT_INQUIRY

    def test_account_issue(self):
        intent, confidence = _fast_intent_classify("我忘记密码了怎么登录")
        assert intent == IntentType.ACCOUNT_ISSUE

    def test_technical_issue(self):
        intent, confidence = _fast_intent_classify("页面打不开一直转圈")
        assert intent == IntentType.TECHNICAL_ISSUE

    def test_human_handoff(self):
        intent, confidence = _fast_intent_classify("给我转人工")
        assert intent == IntentType.HUMAN_HANDOFF

    def test_unknown_intent(self):
        intent, confidence = _fast_intent_classify("今天天气不错")
        assert intent is None
        assert confidence == 0.0


class TestBERTIntentClassifier:
    """Tests for the BERT-based IntentClassifier with mocked model."""

    @pytest.fixture(autouse=True)
    def _setup_classifier(self):
        """Reset singleton and set up controlled prototypes for each test."""
        import src.agent.nodes.intent_classifier as ic
        ic.IntentClassifier._instance = None

        self._rng = np.random.RandomState(42)
        self._dim = 512
        self._labels = [e for e in IntentType if e != IntentType.SLOT_FILLING]

        # Deterministic normalized prototype vectors
        self._prototypes = self._rng.randn(len(self._labels), self._dim).astype(np.float32)
        self._prototypes /= np.linalg.norm(self._prototypes, axis=1, keepdims=True)

        self._classifier = ic.IntentClassifier.get_instance()
        self._classifier._labels = self._labels
        self._classifier._prototypes = self._prototypes

        self._mock_model = MagicMock()
        self._classifier._model = self._mock_model

    def _set_target(self, target_label: IntentType):
        """Configure mock encode to return a vector biased toward target_label."""
        idx = self._labels.index(target_label)
        target = self._prototypes[idx]

        def mock_encode(texts, normalize_embeddings=True, show_progress_bar=False):
            noise = self._rng.randn(self._dim).astype(np.float32)
            noise /= np.linalg.norm(noise)
            query = 0.80 * target + 0.20 * noise
            query /= np.linalg.norm(query)
            return np.array([query], dtype=np.float32)

        self._mock_model.encode = mock_encode

    @pytest.mark.asyncio
    async def test_complaint_intent(self):
        self._set_target(IntentType.COMPLAINT)
        intent, confidence = await self._classifier.classify("你们客服态度太差了我要投诉")
        assert intent == IntentType.COMPLAINT
        assert confidence > 0.5

    @pytest.mark.asyncio
    async def test_logistics_intent(self):
        self._set_target(IntentType.LOGISTICS_QUERY)
        intent, confidence = await self._classifier.classify("我的快递到哪了")
        assert intent == IntentType.LOGISTICS_QUERY
        assert confidence > 0.5

    @pytest.mark.asyncio
    async def test_product_inquiry_intent(self):
        self._set_target(IntentType.PRODUCT_INQUIRY)
        intent, confidence = await self._classifier.classify("这是什么材质的")
        assert intent == IntentType.PRODUCT_INQUIRY
        assert confidence > 0.5

    @pytest.mark.asyncio
    async def test_order_status_intent(self):
        self._set_target(IntentType.ORDER_STATUS)
        intent, confidence = await self._classifier.classify("我的订单发货了吗")
        assert intent == IntentType.ORDER_STATUS
        assert confidence > 0.5

    @pytest.mark.asyncio
    async def test_human_handoff_intent(self):
        self._set_target(IntentType.HUMAN_HANDOFF)
        intent, confidence = await self._classifier.classify("我要转人工客服")
        assert intent == IntentType.HUMAN_HANDOFF
        assert confidence > 0.5

    @pytest.mark.asyncio
    async def test_return_request_intent(self):
        self._set_target(IntentType.RETURN_REQUEST)
        intent, confidence = await self._classifier.classify("这个质量不好想退货")
        assert intent == IntentType.RETURN_REQUEST
        assert confidence > 0.5

    @pytest.mark.asyncio
    async def test_refund_inquiry_intent(self):
        self._set_target(IntentType.REFUND_INQUIRY)
        intent, confidence = await self._classifier.classify("退款什么时候到账")
        assert intent == IntentType.REFUND_INQUIRY
        assert confidence > 0.5

    @pytest.mark.asyncio
    async def test_technical_issue_intent(self):
        self._set_target(IntentType.TECHNICAL_ISSUE)
        intent, confidence = await self._classifier.classify("app打不开一直闪退")
        assert intent == IntentType.TECHNICAL_ISSUE
        assert confidence > 0.5

    @pytest.mark.asyncio
    async def test_account_issue_intent(self):
        self._set_target(IntentType.ACCOUNT_ISSUE)
        intent, confidence = await self._classifier.classify("忘记密码怎么找回")
        assert intent == IntentType.ACCOUNT_ISSUE
        assert confidence > 0.5

    @pytest.mark.asyncio
    async def test_modify_order_intent(self):
        self._set_target(IntentType.MODIFY_ORDER)
        intent, confidence = await self._classifier.classify("帮我修改一下收货地址")
        assert intent == IntentType.MODIFY_ORDER
        assert confidence > 0.5

    @pytest.mark.asyncio
    async def test_classify_top_k(self):
        self._set_target(IntentType.COMPLAINT)
        results = await self._classifier.classify_top_k("我要投诉", k=3)
        assert len(results) == 3
        assert results[0][0] == IntentType.COMPLAINT
        assert results[0][1] > results[1][1]  # top confidence > second

    @pytest.mark.asyncio
    async def test_singleton(self):
        import src.agent.nodes.intent_classifier as ic
        instance2 = ic.IntentClassifier.get_instance()
        assert instance2 is self._classifier
