#
# Copyright (C) 2016 Jerome Kelleher <jerome.kelleher@well.ox.ac.uk>
#
# This file is part of msprime.
#
# msprime is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# msprime is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with msprime.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Test cases for branch length statistic computation.
"""
from __future__ import print_function
from __future__ import division


import unittest
import random

import msprime
import _msprime

##
# This tests implementation of the algorithm described in branch-lengths-methods.md
##


def build_tree_sequence(records, mutations=[]):
    ts = _msprime.TreeSequence()
    # quick workaround to get the samples.
    # NOTE this is a temporary workaround; the planned API will import nodes,
    # edgesets and mutations.
    sample_size = min(record.node for record in records)
    samples = [(0, 0) for _ in range(sample_size)]
    ts.load_records(samples, records, mutations)
    return msprime.TreeSequence(ts)


def path_length(tr, x, y):
    L = 0
    mrca = tr.mrca(x, y)
    for u in x, y:
        while u != mrca:
            L += tr.branch_length(u)
            u = tr.parent(u)
    return L


def branch_length_diversity(ts, X, Y):
    '''
    Computes average pairwise diversity between a random choice from x
    and a random choice from y.
    '''
    S = 0
    for tr in ts.trees():
        SS = 0
        for x in X:
            for y in Y:
                SS += path_length(tr, x, y)
        S += SS*tr.length
    return S/(ts.sequence_length*len(X)*len(Y))


def branch_length_Y(ts, x, y, z):
    S = 0
    for tr in ts.trees():
        xy_mrca = tr.mrca(x, y)
        xz_mrca = tr.mrca(x, z)
        yz_mrca = tr.mrca(y, z)
        if xy_mrca == xz_mrca:
            #   /\
            #  / /\
            # x y  z
            S += path_length(tr, x, yz_mrca)*tr.length
        elif xy_mrca == yz_mrca:
            #   /\
            #  / /\
            # y x  z
            S += path_length(tr, x, xz_mrca)*tr.length
        elif xz_mrca == yz_mrca:
            #   /\
            #  / /\
            # z x  y
            S += path_length(tr, x, xy_mrca)*tr.length
    return S/ts.sequence_length


def branch_length_f4(ts, A, B, C, D):
    for U in A, B, C, D:
        if max([U.count(x) for x in set(U)]) > 1:
            raise ValueError("A,B,C, and D cannot contain repeated elements.")
    S = 0
    for tr in ts.trees():
        SS = 0
        for a in A:
            for b in B:
                for c in C:
                    for d in D:
                        SS += path_length(tr, tr.mrca(a, c), tr.mrca(b, d))
                        SS -= path_length(tr, tr.mrca(a, d), tr.mrca(b, c))
        S += SS*tr.length
    return S/(ts.sequence_length*len(A)*len(B)*len(C)*len(D))


def branch_stats_node_iter(ts, leaf_sets, weight_fun, method='length'):
    '''
    Here leaf_sets is a list of lists of leaves, and weight_fun is a function
    whose argument is a list of integers of the same length as leaf_sets
    that returns a number.  Each branch in a tree is weighted by weight_fun(x),
    where x[i] is the number of leaves in leaf_sets[i] below that
    branch.  This finds the sum of all counted branches for each tree,
    and averages this across the tree sequence ts, weighted by genomic length.

    If method='mutations' instead, then branch lengths will be measured in
    numbers of mutations instead of time.

    This version is inefficient as it iterates over all nodes in each tree.
    '''
    out = branch_stats_vector_node_iter(ts, leaf_sets, lambda x: [weight_fun(x)], method)
    if len(out) > 1:
        raise ValueError("Expecting output of length 1.")
    return out[0]


def branch_stats_vector_node_iter(ts, leaf_sets, weight_fun, method='length'):
    '''
    Here leaf_sets is a list of lists of leaves, and weight_fun is a function
    whose argument is a list of integers of the same length as leaf_sets
    that returns a list of numbers; there will be one output for each element.
    For each value, each branch in a tree is weighted by weight_fun(x),
    where x[i] is the number of leaves in leaf_sets[i] below that
    branch.  This finds the sum of all counted branches for each tree,
    and averages this across the tree sequence ts, weighted by genomic length.

    If method='mutations' instead, then branch lengths will be measured in
    numbers of mutations instead of time.

    This version is inefficient as it iterates over all nodes in each tree.
    '''
    for U in leaf_sets:
        if max([U.count(x) for x in set(U)]) > 1:
            raise ValueError("elements of leaf_sets cannot contain repeated elements.")
    tr_its = [ts.trees(
        tracked_leaves=x,
        leaf_counts=True,
        leaf_lists=True) for x in leaf_sets]
    n_out = len(weight_fun([0 for a in leaf_sets]))
    S = [0.0 for j in range(n_out)]
    for k in range(ts.num_trees):
        trs = [next(x) for x in tr_its]
        root = trs[0].root
        tr_len = trs[0].length
        if method == 'length':
            for node in trs[0].nodes():
                if node != root:
                    x = [tr.num_tracked_leaves(node) for tr in trs]
                    w = weight_fun(x)
                    for j in range(n_out):
                        S[j] += w[j] * trs[0].branch_length(node) * tr_len
        elif method == 'mutations':
            count_nodes = dict(
                [(node, weight_fun([tr.num_tracked_leaves(node) for tr in trs]))
                    for node in trs[0].nodes() if node != root])
            # print(count_nodes)
            for mut in trs[0].mutations():
                # print(mut)
                for j in range(n_out):
                    # TODO: this is the theoretical method
                    # that assumes we can distinguish recurrent mutations
                    for mn in mut.nodes:
                        S[j] += count_nodes[mn][j]
        else:
            raise(TypeError("Unknown method "+method))
    for j in range(n_out):
        S[j] /= ts.get_sequence_length()
    return S


class BranchStatsTestCase(unittest.TestCase):
    """
    Tests of branch statistic computation.
    """
    random_seed = 123456

    def assertListAlmostEqual(self, x, y):
        for a, b in zip(x, y):
            self.assertAlmostEqual(a, b)

    def check_vectorization(self, ts):
        samples = random.sample(ts.samples(), 3)
        A = [[samples[0]], [samples[1]], [samples[2]]]

        def f(x):
            return [float((x[0] > 0) != (x[1] > 0)),
                    float((x[0] > 0) != (x[2] > 0)),
                    float((x[1] > 0) != (x[2] > 0))]

        self.assertListAlmostEqual(
                branch_stats_vector_node_iter(ts, A, f, method='mutations'),
                [ts.pairwise_diversity(samples=[samples[0], samples[1]]),
                 ts.pairwise_diversity(samples=[samples[0], samples[2]]),
                 ts.pairwise_diversity(samples=[samples[1], samples[2]])])
        self.assertListAlmostEqual(
                branch_stats_vector_node_iter(ts, A, f, method='length'),
                [branch_length_diversity(ts, A[0], A[1]),
                 branch_length_diversity(ts, A[0], A[2]),
                 branch_length_diversity(ts, A[1], A[2])])
        self.assertListAlmostEqual(
                ts.branch_stats_vector(A, f),
                [branch_length_diversity(ts, A[0], A[1]),
                 branch_length_diversity(ts, A[0], A[2]),
                 branch_length_diversity(ts, A[1], A[2])])

    def check_pairwise_diversity(self, ts):
        samples = random.sample(ts.samples(), 2)
        A_one = [[samples[0]], [samples[1]]]
        A_many = [random.sample(ts.samples(), 2),
                  random.sample(ts.samples(), 2)]
        for A in (A_one, A_many):
            n = [len(a) for a in A]

            def f(x):
                return float(x[0]*(n[1]-x[1]) + (n[0]-x[0])*x[1])/float(n[0]*n[1])

            self.assertAlmostEqual(
                    branch_stats_node_iter(ts, A, f, method='length'),
                    branch_length_diversity(ts, A[0], A[1]))
            self.assertAlmostEqual(
                    ts.branch_stats(A, f),
                    branch_length_diversity(ts, A[0], A[1]))

    def check_pairwise_diversity_mutations(self, ts):
        samples = random.sample(ts.samples(), 2)
        A = [[samples[0]], [samples[1]]]
        n = [len(a) for a in A]

        def f(x):
            return float(x[0]*(n[1]-x[1]) + (n[0]-x[0])*x[1])/float(n[0]*n[1])

        self.assertAlmostEqual(
                branch_stats_node_iter(ts, A, f, method='mutations'),
                ts.pairwise_diversity(samples=samples))

    def check_Y_stat(self, ts):
        samples = random.sample(ts.samples(), 3)
        A = [[samples[0]], samples[1:3]]

        def f(x):
            return float(((x[0] == 1) and (x[1] == 0)) or ((x[0] == 0) and (x[1] == 2)))

        self.assertAlmostEqual(
                ts.branch_stats(A, f),
                branch_length_Y(ts, A[0][0], A[1][0], A[1][1]))
        self.assertAlmostEqual(
                branch_stats_node_iter(ts, A, f, method='length'),
                branch_length_Y(ts, A[0][0], A[1][0], A[1][1]))

    def check_f4_stat(self, ts):
        samples = random.sample(ts.samples(), 4)
        A_zero = [[samples[0]], [samples[0]], [samples[1]], [samples[1]]]
        A_f1 = [[samples[0]], [samples[1]], [samples[0]], [samples[1]]]
        A_one = [[samples[0]], [samples[1]], [samples[2]], [samples[3]]]
        A_many = [random.sample(ts.samples(), 3),
                  random.sample(ts.samples(), 3),
                  random.sample(ts.samples(), 3),
                  random.sample(ts.samples(), 3)]
        for A in (A_zero, A_f1, A_one, A_many):

            def f(x):
                return ((float(x[0])/len(A[0])-float(x[1])/len(A[1]))
                        * (float(x[2])/len(A[2])-float(x[3])/len(A[3])))

            self.assertAlmostEqual(
                    ts.branch_stats(A, f),
                    branch_length_f4(ts, A[0], A[1], A[2], A[3]))
            self.assertAlmostEqual(
                    branch_stats_node_iter(ts, A, f, method='length'),
                    branch_length_f4(ts, A[0], A[1], A[2], A[3]))

    def test_pairwise_diversity(self):
        ts = msprime.simulate(10, random_seed=self.random_seed, recombination_rate=100)
        self.check_pairwise_diversity(ts)
        self.check_pairwise_diversity_mutations(ts)

    def test_Y_stat(self):
        ts = msprime.simulate(10, random_seed=self.random_seed, recombination_rate=100)
        self.check_Y_stat(ts)

    def test_f4(self):
        ts = msprime.simulate(10, random_seed=self.random_seed, recombination_rate=100)
        self.check_f4_stat(ts)

    def test_vectorization(self):
        ts = msprime.simulate(10, random_seed=self.random_seed, recombination_rate=100)
        self.check_vectorization(ts)

    def test_case_1(self):
        # With mutations:
        #
        # 1.0          6
        # 0.7         / \                                    5
        #            /   X                                  / \
        # 0.5       X     4                4               /   4
        #          /     / \              / \             /   X X
        # 0.4     X     X   \            X   3           X   /   \
        #        /     /     X          /   / X         /   /     \
        # 0.0   0     1       2        1   0   2       0   1       2
        #          (0.0, 0.2),        (0.2, 0.8),       (0.8, 1.0)
        #

        true_diversity_01 = 2*(1 * (0.2-0) + 0.5 * (0.8-0.2) + 0.7 * (1.0-0.8))
        true_diversity_02 = 2*(1 * (0.2-0) + 0.4 * (0.8-0.2) + 0.7 * (1.0-0.8))
        true_diversity_12 = 2*(0.5 * (0.2-0) + 0.5 * (0.8-0.2) + 0.5 * (1.0-0.8))

        records = [
            msprime.CoalescenceRecord(
                left=0.2, right=0.8, node=3, children=(0, 2),
                time=0.4, population=0),
            msprime.CoalescenceRecord(
                left=0.0, right=0.2, node=4, children=(1, 2),
                time=0.5, population=0),
            msprime.CoalescenceRecord(
                left=0.2, right=0.8, node=4, children=(1, 3),
                time=0.5, population=0),
            msprime.CoalescenceRecord(
                left=0.8, right=1.0, node=4, children=(1, 2),
                time=0.5, population=0),
            msprime.CoalescenceRecord(
                left=0.8, right=1.0, node=5, children=(0, 4),
                time=0.7, population=0),
            msprime.CoalescenceRecord(
                left=0.0, right=0.2, node=6, children=(0, 4),
                time=1.0, population=0)]

        mutations = [
            (0.05, (4,)),
            (0.1, (0,)),
            (0.11, (2,)),
            (0.15, (0,)),
            (0.151, (1,)),
            (0.3, (1,)),
            (0.6, (2,)),
            (0.9, (0,)),
            (0.95, (1,)),
            (0.951, (2,))]
        ts = build_tree_sequence(records, mutations)

        self.check_pairwise_diversity(ts)
        self.check_pairwise_diversity_mutations(ts)
        self.check_Y_stat(ts)
        self.check_vectorization(ts)

        # diversity between 0 and 1
        A = [[0], [1]]

        def f(x):
            return float((x[0] > 0) != (x[1] > 0))

        # branch lengths:
        self.assertAlmostEqual(branch_length_diversity(ts, [0], [1]),
                               true_diversity_01)
        self.assertAlmostEqual(ts.branch_stats(A, f),
                               true_diversity_01)
        self.assertAlmostEqual(branch_stats_node_iter(ts, A, f),
                               true_diversity_01)

        # mean diversity between [0, 1] and [0, 2]:
        true_mean_diversity = (0 + true_diversity_02
                               + true_diversity_01 + true_diversity_12)/4
        A = [[0, 1], [0, 2]]
        n = [len(a) for a in A]

        def f(x):
            return float(x[0]*(n[1]-x[1]) + (n[0]-x[0])*x[1])/4.0

        # branch lengths:
        self.assertAlmostEqual(branch_length_diversity(ts, A[0], A[1]),
                               true_mean_diversity)
        self.assertAlmostEqual(ts.branch_stats(A, f),
                               true_mean_diversity)
        self.assertAlmostEqual(branch_stats_node_iter(ts, A, f),
                               true_mean_diversity)

        # Y-statistic for (0/12)
        A = [[0], [1, 2]]

        def f(x):
            return ((x[0] == 1) and (x[1] == 0)) or ((x[0] == 0) and (x[1] == 2))

        # branch lengths:
        true_Y = 0.2*(1 + 0.5) + 0.6*(0.4) + 0.2*(0.7+0.2)
        self.assertAlmostEqual(branch_length_Y(ts, 0, 1, 2), true_Y)
        self.assertAlmostEqual(ts.branch_stats(A, f), true_Y)
        self.assertAlmostEqual(branch_stats_node_iter(ts, A, f), true_Y)

    def test_case_2(self):
        # Here are the trees:
        # t                  |              |              |             |
        #
        # 0       --3--      |     --3--    |     --3--    |    --3--    |    --3--
        #        /  |  \     |    /  |  \   |    /     \   |   /     \   |   /     \
        # 1     4   |   5    |   4   |   5  |   4       5  |  4       5  |  4       5
        #       |\ / \ /|    |   |\   \     |   |\     /   |  |\     /   |  |\     /|
        # 2     | 6   7 |    |   | 6   7    |   | 6   7    |  | 6   7    |  | 6   7 |
        #       | |\ /| |    |   |  \  |    |   |  \  |    |  |  \       |  |  \    | ...
        # 3     | | 8 | |    |   |   8 |    |   |   8 |    |  |   8      |  |   8   |
        #       | |/ \| |    |   |  /  |    |   |  /  |    |  |  / \     |  |  / \  |
        # 4     | 9  10 |    |   | 9  10    |   | 9  10    |  | 9  10    |  | 9  10 |
        #       |/ \ / \|    |   |  \   \   |   |  \   \   |  |  \   \   |  |  \    |
        # 5     0   1   2    |   0   1   2  |   0   1   2  |  0   1   2  |  0   1   2
        #
        #                    |   0.0 - 0.1  |   0.1 - 0.2  |  0.2 - 0.4  |  0.4 - 0.5
        # ... continued:
        # t                  |             |             |             |
        #
        # 0         --3--    |    --3--    |    --3--    |    --3--    |    --3--
        #          /     \   |   /     \   |   /     \   |   /     \   |   /  |  \
        # 1       4       5  |  4       5  |  4       5  |  4       5  |  4   |   5
        #         |\     /|  |   \     /|  |   \     /|  |   \     /|  |     /   /|
        # 2       | 6   7 |  |    6   7 |  |    6   7 |  |    6   7 |  |    6   7 |
        #         |  \    |  |     \    |  |       /  |  |    |  /  |  |    |  /  |
        # 3  ...  |   8   |  |      8   |  |      8   |  |    | 8   |  |    | 8   |
        #         |  / \  |  |     / \  |  |     / \  |  |    |  \  |  |    |  \  |
        # 4       | 9  10 |  |    9  10 |  |    9  10 |  |    9  10 |  |    9  10 |
        #         |    /  |  |   /   /  |  |   /   /  |  |   /   /  |  |   /   /  |
        # 5       0   1   2  |  0   1   2  |  0   1   2  |  0   1   2  |  0   1   2
        #
        #         0.5 - 0.6  |  0.6 - 0.7  |  0.7 - 0.8  |  0.8 - 0.9  |  0.9 - 1.0

        # divergence betw 0 and 1
        true_diversity_01 = 2*(0.6*4 + 0.2*2 + 0.2*5)
        # divergence betw 1 and 2
        true_diversity_12 = 2*(0.2*5 + 0.2*2 + 0.3*5 + 0.3*4)
        # divergence betw 0 and 2
        true_diversity_02 = 2*(0.2*5 + 0.2*4 + 0.3*5 + 0.1*4 + 0.2*5)
        # mean divergence between 0, 1 and 0, 2
        true_mean_diversity = (0 + true_diversity_02
                               + true_diversity_01 + true_diversity_12)/4
        # Y(0;1, 2)
        true_Y = 0.2*4 + 0.2*(4+2) + 0.2*4 + 0.2*2 + 0.2*(5+1)

        records = [
                msprime.CoalescenceRecord(
                    left=0.5, right=1.0, node=10, children=(1,),
                    time=5.0-4.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.0, right=0.4, node=10, children=(2,),
                    time=5.0-4.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.6, right=1.0, node=9, children=(0,),
                    time=5.0-4.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.0, right=0.5, node=9, children=(1,),
                    time=5.0-4.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.8, right=1.0, node=8, children=(10,),
                    time=5.0-3.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.2, right=0.8, node=8, children=(9, 10),
                    time=5.0-3.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.0, right=0.2, node=8, children=(9,),
                    time=5.0-3.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.7, right=1.0, node=7, children=(8,),
                    time=5.0-2.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.0, right=0.2, node=7, children=(10,),
                    time=5.0-2.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.8, right=1.0, node=6, children=(9,),
                    time=5.0-2.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.0, right=0.7, node=6, children=(8,),
                    time=5.0-2.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.4, right=1.0, node=5, children=(2, 7),
                    time=5.0-1.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.1, right=0.4, node=5, children=(7,),
                    time=5.0-1.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.6, right=0.9, node=4, children=(6,),
                    time=5.0-1.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.0, right=0.6, node=4, children=(0, 6),
                    time=5.0-1.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.9, right=1.0, node=3, children=(4, 5, 6),
                    time=5.0-0.0, population=0),
                msprime.CoalescenceRecord(
                    left=0.1, right=0.9, node=3, children=(4, 5),
                    time=5.0-0.0, population=0),
                msprime.CoalescenceRecord(
                        left=0.0, right=0.1, node=3, children=(4, 5, 7),
                        time=5.0-0.0, population=0),
               ]

        ts = build_tree_sequence(records)

        self.check_pairwise_diversity(ts)
        self.check_pairwise_diversity_mutations(ts)
        self.check_Y_stat(ts)
        self.check_vectorization(ts)

        # divergence between 0 and 1
        A = [[0], [1]]

        def f(x):
            return (x[0] > 0) != (x[1] > 0)

        # branch lengths:
        self.assertAlmostEqual(branch_length_diversity(ts, [0], [1]),
                               true_diversity_01)
        self.assertAlmostEqual(ts.branch_stats(A, f),
                               true_diversity_01)
        self.assertAlmostEqual(branch_stats_node_iter(ts, A, f),
                               true_diversity_01)

        # mean divergence between 0, 1 and 0, 2
        A = [[0, 1], [0, 2]]
        n = [len(a) for a in A]

        def f(x):
            return float(x[0]*(n[1]-x[1]) + (n[0]-x[0])*x[1])/4.0

        # branch lengths:
        self.assertAlmostEqual(branch_length_diversity(ts, A[0], A[1]),
                               true_mean_diversity)
        self.assertAlmostEqual(ts.branch_stats(A, f),
                               true_mean_diversity)
        self.assertAlmostEqual(branch_stats_node_iter(ts, A, f),
                               true_mean_diversity)

        # Y-statistic for (0/12)
        A = [[0], [1, 2]]

        def f(x):
            return ((x[0] == 1) and (x[1] == 0)) or ((x[0] == 0) and (x[1] == 2))

        # branch lengths:
        self.assertAlmostEqual(branch_length_Y(ts, 0, 1, 2), true_Y)
        self.assertAlmostEqual(ts.branch_stats(A, f), true_Y)
        self.assertAlmostEqual(branch_stats_node_iter(ts, A, f), true_Y)