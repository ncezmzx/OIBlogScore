# 后缀自动机：endpos 与 clone

## 问题模型

为单串构建识别所有子串的转移图；非根状态代表相同结束位置集合 endpos 的非空子串类。计数或多串构造需明确使用变体。

## 算法原理

从 last 加入新字符并沿 suffix link 补缺边。若发现已有边 p→q 且 `len[p]+1<len[q]`，复制 q 的转移和 link，设 clone 长度为 len[p]+1，重定向应拆开的转移，并让 q 和新节点的 link 指向 clone。

## 成立条件

一个状态的连续长度区间为 `[len[link[v]]+1,len[v]]`；`len` 是类中最长串，不是深度。标准构建从空串开始，不能不加区分把多个串直接连续 extend 后声称不会产生跨串子串。

## 关键不变量

suffix link 指向最长、且 endpos 已扩大到其他类的真后缀；clone 代表分裂的历史等价类，不表示新的前缀结尾事件。

## 证明路线

沿 link 只更新新串会影响到的后缀；若既有 q 的长度连续性被打破，分裂并重定向正好区分新出现与仍保留的 endpos。计数时每个实际前缀末态记 1，降 len 沿 link 聚合，可恢复各类 endpos 数。

## 复杂度推导

固定字母表、常数转移访问下标准单串构建 O(n)，状态和边线性；排序可按 len 计数。映射实现须计 O(log σ) 查找及 clone 拷贝，不能仅数 extend 调用次数就得线性。

## 错误与反例

构建 `abb` 会分裂出类 `b` 的 clone；`b` 两次出现，若给 clone 初始计数 1 又叠加前缀末态贡献，会得到 3。

## 性质边界

边上每次读字符；suffix link 自身不消耗字符，不是 Trie 父边。`Σ(len[v]−len[link[v]])` 只对非根正确构造的单串状态计不同子串。

## 审稿检查

追踪 `abb` 的 q/clone、重定向条件、计数初始化和降序传播；核对 last 对应整个已读前缀，避免把转移埋在错误的 p 跳转之后。

## 区别与联系

后缀数组给显式字典序与相邻 LCP；SAM 利用终点集合，适合子串可达、不同子串与出现次数。

## 依据

[CP-Algorithms：Suffix automaton](https://cp-algorithms.com/string/suffix-automaton.html)。

相关专题：[后缀数组](../strings/suffix-array.md)。
