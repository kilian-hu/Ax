#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from unittest import mock

import torch
from ax.core.search_space import SearchSpaceDigest
from ax.models.torch.rembo import REMBO
from ax.utils.common.testutils import TestCase
from ax.utils.testing.mock import fast_botorch_optimize
from botorch.utils.datasets import FixedNoiseDataset


class REMBOTest(TestCase):
    @fast_botorch_optimize
    def testREMBOModel(self):
        A = torch.cat((torch.eye(2), -(torch.eye(2))))
        initial_X_d = torch.tensor([[0.25, 0.5], [1, 0], [0, -1]])
        bounds_d = [(-2, 2), (-2, 2)]
        my_metric_names = ["a", "b"]

        # Test setting attributes
        m = REMBO(A=A, initial_X_d=initial_X_d, bounds_d=bounds_d)
        self.assertTrue(torch.allclose(A, m.A))
        self.assertTrue(torch.allclose(torch.pinverse(A), m._pinvA))
        self.assertEqual(m.bounds_d, bounds_d)
        self.assertEqual(len(m.X_d), 3)

        # Test fit
        # Create high-D data
        X_D = torch.t(torch.mm(A, torch.t(initial_X_d)))
        datasets = [
            FixedNoiseDataset(X=X_D, Y=torch.randn(3, 1), Yvar=0.1 * torch.ones(3, 1)),
        ] * 2

        Xs = [X_D, X_D.clone()]
        Ys = [torch.randn(3, 1)] * 2
        Yvars = [0.1 * torch.ones(3, 1)] * 2
        datasets = [
            FixedNoiseDataset(X=X, Y=Y, Yvar=Yvar) for X, Y, Yvar in zip(Xs, Ys, Yvars)
        ]

        bounds = [(-1, 1)] * 4
        with self.assertRaises(AssertionError):
            m.fit(
                datasets=datasets,
                metric_names=my_metric_names,
                search_space_digest=SearchSpaceDigest(
                    feature_names=[],
                    bounds=[(0, 1)] * 4,
                ),
            )

        m.fit(
            datasets=datasets,
            metric_names=my_metric_names,
            search_space_digest=SearchSpaceDigest(
                feature_names=[],
                bounds=bounds,
            ),
        )

        # Check was fit with the low-d data.
        for x in m.Xs:
            self.assertTrue(torch.allclose(x, m.to_01(initial_X_d)))

        self.assertEqual(len(m.X_d), 3)

        # Test project up
        X_d2 = torch.tensor([[0.25, 0.5], [2.0, 0.0], [-4.0, 4.0]])
        X_D2 = torch.tensor(
            [[0.25, 0.5, -0.25, -0.5], [1.0, 0.0, -1.0, 0.0], [-1.0, 1.0, 1.0, -1.0]]
        )
        Z = m.project_up(X_d2)
        self.assertTrue(torch.allclose(Z, X_D2))

        # Test predict
        f1, var = m.predict(X=X_D)
        self.assertEqual(f1.shape, torch.Size([3, 2]))
        with self.assertRaises(NotImplementedError):
            m.predict(torch.tensor([[0.1, 0.2, 0.3, 0.4]]))

        f2, var = m.predict(initial_X_d)
        self.assertTrue(torch.allclose(f1, f2))

        # Test best_point
        x_best = m.best_point(
            bounds=[(-1, 1)] * 4, objective_weights=torch.tensor([1.0, 0.0])
        )
        self.assertEqual(len(x_best), 4)

        # Test cross_validate
        f, var = m.cross_validate(
            datasets=[
                FixedNoiseDataset(
                    X=X_D[:-1, :], Y=Ys[0][:-1, :], Yvar=Yvars[0][:-1, :]
                ),
                FixedNoiseDataset(
                    X=X_D[:-1, :], Y=Ys[1][:-1, :], Yvar=Yvars[1][:-1, :]
                ),
            ],
            X_test=X_D[-1:, :],
        )
        self.assertEqual(f.shape, torch.Size([1, 2]))

        # Test gen
        Xgen_d = torch.tensor([[0.4, 0.8], [-0.2, 1.0]])
        acqfv_dummy = torch.tensor([[0.0, 0.0], [0.0, 0.0]])
        with mock.patch(
            "ax.models.torch.botorch_defaults.optimize_acqf",
            autospec=True,
            return_value=(Xgen_d, acqfv_dummy),
        ):
            gen_results = m.gen(
                n=2, bounds=[(-1, 1)] * 4, objective_weights=torch.tensor([1.0, 0.0])
            )

        self.assertEqual(gen_results.points.shape[1], 4)
        self.assertEqual(len(m.X_d), 5)

        # Test update
        with self.assertRaises(ValueError):
            new_dataset = FixedNoiseDataset(
                X=torch.tensor([[0.1, 0.2, 0.3, 0.4]]),
                Y=torch.randn(1, 1),
                Yvar=torch.ones(1, 1),
            )
            m.update(datasets=[new_dataset, new_dataset])

        new_dataset = FixedNoiseDataset(
            X=gen_results.points,
            Y=torch.randn(2, 1),
            Yvar=torch.ones(2, 1),
        )
        m.update(datasets=[new_dataset, new_dataset])
        for x in m.Xs:
            self.assertTrue(torch.allclose(x, Xgen_d))
