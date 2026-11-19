# 数论：同余、逆元和非互素 CRT

## 问题模型

正模数 m 下处理同余、乘法逆元及合并 `x≡a (mod m), x≡b (mod n)`。

## 算法原理

扩展欧几里得求 Bezout 系数。设 x=a+mt，把合并化为 `mt≡b−a (mod n)`；除 gcd 后求 t 的模逆并还原。

## 成立条件

逆元存在当且仅当 gcd(a,m)=1；CRT 可合并当且仅当 gcd(m,n) 整除 b−a。用费马 `a^(p−2)` 需 p 素且 p 不整除 a。

## 关键不变量

扩欧返回的系数满足整数恒等式；逐步合并后用一个模 lcm 的余数类精确表示当前所有解。

## 证明路线

由整数线性组合证明必要性；除去 gcd 后系数互素，得到构造，所有 t 的差为 n/g 的倍数，故所有 x 相差 lcm 的倍数。

## 复杂度推导

单次欧几里得 O(log max(m,n)) 次整除；逐次合并要按增长后的模数计位长。机器字内先除再乘也不能保证 lcm 不溢出。

## 错误与反例

模 4 的 2 无逆；`x≡0 (mod 4)` 且 `x≡1 (mod 6)` 无解，不能套互素 CRT 乘积公式。

## 性质边界

C++ 负余数不是数学规范余数；除法在模环里不是先做整数 `/` 后取模。避免用 (a+m) 在机器字上不经范围检查。

## 审稿检查

检查模数是否可为 1、分母是否为单位、余数与系数范围以及乘法类型。用非互素一致和不一致两组样例验证。

## 区别与联系

NTT 在特殊素域需要单位根阶；线性代数消元也依赖主元可逆，复合模上的非零不等于可逆。

## 依据

[CP-Algorithms：模逆](https://cp-algorithms.com/algebra/module-inverse.html) 与 [CRT](https://cp-algorithms.com/algebra/chinese-remainder-theorem.html)。

相关专题：[NTT](../divide-and-conquer/fft-ntt.md)、[线性代数](../mathematics/linear-algebra.md)。
