import unittest
from unittest.mock import Mock, patch

from social_core.pipeline.partial import partial, partial_step
from social_core.utils import PARTIAL_TOKEN_SESSION_NAME


class PartialDecoratorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.mock_current_partial_token = Mock()
        self.mock_current_partial = Mock(token=self.mock_current_partial_token)

        self.mock_strategy = Mock()
        self.mock_backend = Mock()
        self.mock_pipeline_index = Mock()
        self.mock_partial_store = Mock()
        self.mock_strategy.storage.partial.store = self.mock_partial_store

        self.mock_session_set = Mock()
        self.mock_strategy.session_set = self.mock_session_set

    def test_save_to_session(self) -> None:
        # GIVEN
        expected_response = Mock()

        @partial_step(save_to_session=True)
        def decorated_func(*args, **kwargs):
            return expected_response

        # WHEN
        with patch(
            "social_core.pipeline.partial.partial_prepare",
            return_value=self.mock_current_partial,
        ):
            response = decorated_func(
                self.mock_strategy, self.mock_backend, self.mock_pipeline_index
            )

            # THEN
            self.assertEqual(expected_response, response)

            self.assertEqual(1, self.mock_partial_store.call_count)
            self.assertEqual(
                (self.mock_current_partial,), self.mock_partial_store.call_args[0]
            )

            self.assertEqual(1, self.mock_session_set.call_count)
            self.assertEqual(
                (PARTIAL_TOKEN_SESSION_NAME, self.mock_current_partial_token),
                self.mock_session_set.call_args[0],
            )

    def test_not_to_save_to_session(self) -> None:
        # GIVEN
        expected_response = Mock()

        @partial_step(save_to_session=False)
        def decorated_func(*args, **kwargs):
            return expected_response

        # WHEN
        with patch(
            "social_core.pipeline.partial.partial_prepare",
            return_value=self.mock_current_partial,
        ):
            response = decorated_func(
                self.mock_strategy, self.mock_backend, self.mock_pipeline_index
            )

            # THEN
            self.assertEqual(expected_response, response)

            self.assertEqual(1, self.mock_partial_store.call_count)
            self.assertEqual(
                (self.mock_current_partial,), self.mock_partial_store.call_args[0]
            )

            self.assertEqual(0, self.mock_session_set.call_count)

    def test_save_to_session_by_backward_compatible_decorator(self) -> None:
        # GIVEN
        expected_response = Mock()

        @partial
        def decorated_func(*args, **kwargs):
            return expected_response

        # WHEN
        with patch(
            "social_core.pipeline.partial.partial_prepare",
            return_value=self.mock_current_partial,
        ):
            response = decorated_func(
                self.mock_strategy, self.mock_backend, self.mock_pipeline_index
            )

            # THEN
            self.assertEqual(expected_response, response)

            self.assertEqual(1, self.mock_partial_store.call_count)
            self.assertEqual(
                (self.mock_current_partial,), self.mock_partial_store.call_args[0]
            )

            self.assertEqual(1, self.mock_session_set.call_count)
            self.assertEqual(
                (PARTIAL_TOKEN_SESSION_NAME, self.mock_current_partial_token),
                self.mock_session_set.call_args[0],
            )

    def test_not_to_save_to_session_when_the_response_is_a_dict(self) -> None:
        # GIVEN
        expected_response = {"test_key": "test_value"}

        @partial_step(save_to_session=True)
        def decorated_func(*args, **kwargs):
            return expected_response

        # WHEN
        response = decorated_func(
            self.mock_strategy, self.mock_backend, self.mock_pipeline_index
        )

        # THEN
        self.assertEqual(expected_response, response)
        self.assertEqual(0, self.mock_partial_store.call_count)
        self.assertEqual(0, self.mock_session_set.call_count)
