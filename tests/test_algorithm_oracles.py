"""Small independent mathematical checks; not Agent runs or proof certification."""
from itertools import product
import unittest


def count_pairs(points, group_ties):
    groups = []
    for x, y in sorted(points):
        if not groups or not group_ties or groups[-1][0] != x:
            groups.append((x, []))
        groups[-1][1].append(y)

    def solve(lo, hi):
        if hi-lo == 1:
            return 0, groups[lo][1]
        mid = (lo+hi)//2
        a, left = solve(lo, mid)
        b, right = solve(mid, hi)
        j = cross = 0
        for y in right:
            while j < len(left) and left[j] <= y:
                j += 1
            cross += j
        return a+b+cross, sorted(left+right)
    return solve(0, len(groups))[0] if groups else 0


def merge_cost(weights, optimize):
    n = len(weights)
    dp = [[0]*n for _ in weights]
    opt = [[i]*n for i in range(n)]
    sums = [0]
    for w in weights:
        sums.append(sums[-1]+w)
    for length in range(2, n+1):
        for i in range(n-length+1):
            j = i+length-1
            lo, hi = (opt[i][j-1], min(j-1,opt[i+1][j])) if optimize else (i,j-1)
            best, k = min((dp[i][k]+dp[k+1][j], -k) for k in range(lo,hi+1))
            dp[i][j], opt[i][j] = best+sums[j+1]-sums[i], -k
    return dp[0][-1]


class AlgorithmOracles(unittest.TestCase):
    def test_cdq_equal_key_against_ordered_pair_enumeration(self):
        domain = list(product(range(2), repeat=2))
        for n in range(5):
            for points in product(domain, repeat=n):
                expected = sum(x < xx and y <= yy for x, y in points for xx, yy in points)
                self.assertEqual(count_pairs(points, True), expected, points)
        self.assertEqual(count_pairs([(0,0),(0,1)], False), 1)
        self.assertEqual(count_pairs([(0,0),(0,1)], True), 0)

    def test_knuth_including_ties_against_full_interval_dp(self):
        for n in range(1, 7):
            for weights in product(range(3), repeat=n):
                self.assertEqual(merge_cost(weights, True), merge_cost(weights, False), weights)
        self.assertNotEqual(merge_cost((0,0,0,-1), True), merge_cost((0,0,0,-1), False))

    def test_beats_and_pam_witnesses_by_enumeration(self):
        before = [1,2,1,2]
        after = [v + (10 if i < 2 else 0) for i, v in enumerate(before)]
        self.assertEqual(len(set(after)) - len(set(before)), 2)
        s = 'aa'
        longest = [max((s[i:j] for i in range(j) if s[i:j] == s[i:j][::-1]), key=len)
                   for j in range(1, len(s)+1)]
        self.assertEqual(longest.count('a'), 1)
        self.assertEqual(sum(s[i:j]=='a' for i in range(len(s)) for j in range(i+1,len(s)+1)), 2)

    def test_parallel_binary_search_against_first_prefix_enumeration(self):
        queries = [(l,r,k) for l in range(2) for r in range(l,2) for k in range(1,5)]
        for n in range(5):
            for events in product(range(2), repeat=n):
                bounds = [[0,n+1] for _ in queries]
                while any(lo < hi for lo,hi in bounds):
                    buckets = [[] for _ in range(n+1)]
                    for i,(lo,hi) in enumerate(bounds):
                        if lo < hi:
                            buckets[(lo+hi)//2].append(i)
                    counts = [0,0]
                    for mid, bucket in enumerate(buckets):
                        if mid:
                            counts[events[mid-1]] += 1
                        for i in bucket:
                            l,r,k = queries[i]
                            if sum(counts[l:r+1]) >= k:
                                bounds[i][1] = mid
                            else:
                                bounds[i][0] = mid+1
                expected = [next((t for t in range(n+1) if sum(l <= x <= r for x in events[:t]) >= k), n+1)
                            for l,r,k in queries]
                self.assertEqual([lo for lo,_ in bounds], expected)


def simple_lt(graph):
    """Test-only simple link/eval variant; recursion is bounded by fixture size."""
    order, number, parent = [], {}, []
    def dfs(u, p):
        number[u] = len(order)
        order.append(u)
        parent.append(p)
        for v in graph[u]:
            if v not in number:
                dfs(v, number[u])
    dfs(0, -1)
    n = len(order)
    pred, bucket = ([[] for _ in order] for _ in range(2))
    for u in order:
        for v in graph[u]:
            pred[number[v]].append(number[u])
    semi, label = list(range(n)), list(range(n))
    ancestor, idom = [-1]*n, [-1]*n

    def compress(v):
        a = ancestor[v]
        if ancestor[a] != -1:
            compress(a)
            if semi[label[a]] < semi[label[v]]:
                label[v] = label[a]
            ancestor[v] = ancestor[a]

    def evaluate(v):
        if ancestor[v] != -1:
            compress(v)
        return label[v]

    for w in range(n-1, 0, -1):
        semi[w] = min((semi[evaluate(v)] for v in pred[w]), default=w)
        bucket[semi[w]].append(w)
        p = parent[w]
        ancestor[w] = p
        for v in bucket[p]:
            u = evaluate(v)
            idom[v] = u if semi[u] < semi[v] else p
        bucket[p].clear()
    for w in range(1, n):
        if idom[w] != semi[w]:
            idom[w] = idom[idom[w]]
    return {order[w]: order[idom[w]] for w in range(1, n)}


def removal_dominators(graph):
    def reached(removed):
        todo, seen = [0], set()
        while todo:
            u = todo.pop()
            if u == removed or u in seen:
                continue
            seen.add(u)
            todo.extend(graph[u])
        return seen
    reachable = reached(None)
    without = {u: reached(u) for u in reachable}
    dominators = {v: {u for u in reachable if v not in without[u]} for v in reachable}
    return {v: max(dominators[v] - {v}, key=lambda u: len(dominators[u])) for v in reachable - {0}}


class HighRiskOracles(unittest.TestCase):
    def test_simple_lt_against_vertex_removal(self):
        from random import Random
        rng = Random(73109)
        edges = [(u,v) for u in range(4) for v in range(4) if u != v]
        for mask in range(1 << len(edges)):
            graph = [[] for _ in range(4)]
            for i,(u,v) in enumerate(edges):
                if mask >> i & 1:
                    graph[u].append(v)
            self.assertEqual(simple_lt(graph), removal_dominators(graph), graph)
        for _ in range(250):
            graph = [[v for v in range(9) if rng.randrange(5) == 0] for _ in range(9)]
            for row in graph:
                rng.shuffle(row)
            self.assertEqual(simple_lt(graph), removal_dominators(graph), graph)

    def test_matching_augmenting_characterization_against_edge_subsets(self):
        from itertools import combinations
        edges = list(combinations(range(5), 2))
        for mask in range(1 << len(edges)):
            adjacency = {e for i,e in enumerate(edges) if mask >> i & 1}
            matchings = [set(c) for k in range(3) for c in combinations(adjacency, k)
                         if len({v for e in c for v in e}) == 2*k]
            optimum = max(map(len, matchings))
            for matching in matchings:
                exposed = set(range(5)) - {v for e in matching for v in e}
                def has_path(path):
                    if len(path) > 1 and len(path) % 2 == 0 and path[-1] in exposed:
                        return True
                    for v in set(range(5)) - set(path):
                        edge = tuple(sorted((path[-1], v)))
                        if edge in adjacency and (edge in matching) == (len(path) % 2 == 0):
                            if has_path(path+[v]):
                                return True
                    return False
                self.assertEqual(any(has_path([v]) for v in exposed), len(matching) < optimum)

    def test_separator_sam_against_explicit_substrings(self):
        def sam(text):
            edges, link, length = [{}], [-1], [0]
            last = 0
            for c in text:
                u, p = len(edges), last
                edges.append({}); link.append(0); length.append(length[last]+1)
                while p >= 0 and c not in edges[p]:
                    edges[p][c] = u
                    p = link[p]
                if p >= 0:
                    q = edges[p][c]
                    if length[p]+1 == length[q]:
                        link[u] = q
                    else:
                        clone = len(edges)
                        edges.append(dict(edges[q])); link.append(link[q]); length.append(length[p]+1)
                        while p >= 0 and edges[p].get(c) == q:
                            edges[p][c] = clone
                            p = link[p]
                        link[u] = link[q] = clone
                last = u
            return edges
        strings = [''.join(p) for n in range(4) for p in product('ab', repeat=n)]
        queries = [''.join(p) for n in range(1, 5) for p in product('ab', repeat=n)]
        for docs in product(strings, repeat=2):
            edges = sam('#'.join(docs))
            actual = set()
            for q in queries:
                state = 0
                for c in q:
                    state = edges[state].get(c, -1)
                    if state == -1:
                        break
                if state != -1:
                    actual.add(q)
            expected = {s[i:j] for s in docs for i in range(len(s)) for j in range(i+1, len(s)+1)}
            self.assertEqual(actual, expected, docs)
