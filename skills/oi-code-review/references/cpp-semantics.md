# C++ 审查：表达式、边界与生命周期

先登记语言标准、编译器拓展和输入保证，再把博客与代码的变量/下标对应起来。规范依据：[C++ 工作草案](https://eel.is/c++draft/)，[cppreference：UB](https://en.cppreference.com/w/cpp/language/ub.html)。

## Integer Overflow

从输入上界逐步算表达式范围，不从赋值目标反推求值类型。`long long t=a*b;` 若 a,b 是 int，乘法先以 int 求值；应在乘前提升，并验证更宽类型也足够。取模在乘法后并不能修复溢出。INF 相加先要求状态可达，检查最小有符号数的取负和除 −1。

## Signed/Unsigned Conversion

对比较和算式写出通常算术转换后的共同类型。`int i=-1; i < v.size()` 在常见 `size_t` 为无符号且 rank 不低的平台上为假；`v.size()-1` 在空容器下会回绕。无符号回绕有定义但结果未必符合规格，不能与有符号溢出同记为 UB。

## Undefined Behavior

标识可达路径是否读取未初始化对象、执行越界读取、除 0、做超宽/负位移或使用失效引用。不要将“本机输出 e”写成 UB 的语义。标准许可范围与任意编译结果需分开；只在确认编译规格和合法触发条件后报告。

## Array Bounds

为每个索引定义域，检查最大测试、根和哨兵、r+1、遍历空区间以及转移的 k−1。`int a[MAX]; a[MAX]=0;` 不合法，即便位于物理内存附近。将静态池的分配计数与数组槽位编号一起校验，区分 `limit` 是末索引或总数。

## Iterator Invalidation

按实际容器和操作查询无效化规则。[`vector`](https://en.cppreference.com/w/cpp/container/vector.html) 扩容会使已有引用和迭代器失效；未扩容的尾部 push 仍使旧 end 失效。`erase` 后用返回的新迭代器，不把 list 的规则搬给 vector。复现应明确哪次分配/删除发生，不能只凭遍历中出现容器操作判错。

## Reference and Pointer Lifetime

沿引用追到拥有者和最后一次仍存活处。把 `Node& a=pool[i]` 跨 `push_back` 使用要证明没有重新分配，否则存索引并在变动后重新获取。局部对象地址逃逸、临时引用绑定及 lambda 引用捕获与异步调用同样检查。报告位置要包括创建、失效动作及失效后的访问。
