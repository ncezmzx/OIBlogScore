// Authored synthetic witness; the BROKEN path reverses lazy composition.
#include <iostream>
struct Tag {
    bool has_set = false;
    int set = 0;
    int add = 0;
    void append_set(int value) {
        has_set = true;
        set = value;
#ifndef BROKEN
        add = 0;
#endif
    }
    int apply(int original) const { return (has_set ? set : original) + add; }
};
int main() {
    Tag t;
    t.add += 2;
    t.append_set(4);
    std::cout << t.apply(1) << '\n';
}
