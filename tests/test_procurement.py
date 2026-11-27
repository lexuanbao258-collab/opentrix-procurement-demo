# SPDX-FileCopyrightText: 2026 OpenTrix Procurement contributors
# SPDX-License-Identifier: Apache-2.0
import unittest
from unittest.mock import patch

from procurement import RECORDS, ApiError, Client, UnknownOutcome


class WriteOutcomeTest(unittest.TestCase):
    def setUp(self):
        self.client = Client("https://localhost", "https://localhost/token", "test", "test")
        self.client.token = "test"
        self.record_id = "a0000000-0000-4000-8000-000000000001"

    def test_http_500_is_unknown_even_with_a_store_unavailable_code(self):
        for code in ("HTTP_ERROR", "STORE_UNAVAILABLE"):
            with self.subTest(code=code), patch.object(self.client, "_send", side_effect=ApiError(500, code)) as sent:
                with self.assertRaises(UnknownOutcome) as result:
                    self.client.request("POST", RECORDS, body={}, write_id=self.record_id)
                self.assertEqual(result.exception.record_id, self.record_id)
                sent.assert_called_once()

    def test_only_documented_store_unavailable_is_definite(self):
        with patch.object(self.client, "_send", side_effect=ApiError(503, "STORE_UNAVAILABLE")) as sent:
            with self.assertRaises(ApiError):
                self.client.request("POST", RECORDS, body={}, write_id=self.record_id)
            sent.assert_called_once()
