#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import numpy as np
from ax.core.search_space import RobustSearchSpace
from ax.modelbridge.modelbridge_utils import extract_robust_digest
from ax.utils.common.testutils import TestCase
from ax.utils.testing.core_stubs import get_robust_search_space
from ax.utils.testing.core_stubs import get_search_space


class TestModelBridgeUtils(TestCase):
    def test_extract_robust_digest(self):
        # Test with non-robust search space.
        ss = get_search_space()
        self.assertIsNone(extract_robust_digest(ss, list(ss.parameters)))
        # Test with non-environmental search space.
        for multiplicative in (True, False):
            rss = get_robust_search_space(num_samples=8)
            if multiplicative:
                for p in rss.parameter_distributions:
                    p.multiplicative = True
            robust_digest = extract_robust_digest(rss, list(rss.parameters))
            self.assertEqual(robust_digest.multiplicative, multiplicative)
            self.assertEqual(robust_digest.environmental_variables, [])
            samples = robust_digest.distribution_sampler()
            self.assertEqual(samples.shape, (8, 4))
            constructor = np.ones if multiplicative else np.zeros
            self.assertTrue(np.equal(samples[:, 2:], constructor((8, 2))).all())
            # Exponential distribution is non-negative, so we can check for that.
            self.assertTrue(np.all(samples[:, 1] > 0))
            # Check that it works as expected if param_names is missing some
            # non-distributional parameters.
            robust_digest = extract_robust_digest(rss, list(rss.parameters)[:-1])
            samples = robust_digest.distribution_sampler()
            self.assertEqual(samples.shape, (8, 3))
            self.assertTrue(np.equal(samples[:, 2:], constructor((8, 1))).all())
            self.assertTrue(np.all(samples[:, 1] > 0))
            # Check that it errors if we're missing distributional parameters.
            with self.assertRaisesRegex(RuntimeError, "All distributional"):
                extract_robust_digest(rss, list(rss.parameters)[1:])
        # Test with environmental search space.
        all_params = list(rss.parameters.values())
        rss = RobustSearchSpace(
            parameters=all_params[2:],
            parameter_distributions=rss.parameter_distributions,
            num_samples=8,
            environmental_variables=all_params[:2],
        )
        robust_digest = extract_robust_digest(rss, list(rss.parameters))
        self.assertFalse(robust_digest.multiplicative)
        samples = robust_digest.distribution_sampler()
        self.assertEqual(samples.shape, (8, 2))
        # Both are continuous distributions, should be non-zero.
        self.assertTrue(np.all(samples != 0))
        # Check for error if environmental variables are not at the end.
        with self.assertRaisesRegex(RuntimeError, "last entries"):
            extract_robust_digest(rss, list(rss.parameters)[::-1])
