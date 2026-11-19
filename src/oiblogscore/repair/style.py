"""Descriptive prose signals; never author identity or edit authorization."""
from collections import Counter
import re


def style_profile(text):
    text = re.sub(r'\A---\r?\n.*?\r?\n---(?:\r?\n|$)|```.*?```|`[^`\n]+`|\$[^$\n]+\$', '', text, flags=re.S)
    ps = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    sentences = [s.strip() for s in re.split(r'[。！？!?\n]|\.(?=\s|$)', text) if s.strip()]
    vocab = re.findall(r'\b[A-Za-z][A-Za-z0-9_+]*\b|动态规划|线段树|贪心|最短路|复杂度', text)
    phrases = Counter(re.findall(r'就(?:是|行|好)|其实|然后|比如|不妨|我觉得|先.+?再', text))
    mean = sum(map(len, sentences)) / max(1, len(sentences))
    return dict(mean_sentence_chars=mean, mean_paragraph_chars=sum(map(len, ps)) / max(1, len(ps)),
                first_person=len(re.findall(r'我(?:们)?|\bI\b|\bwe\b', text)), vocabulary=Counter(vocab).most_common(15),
                punctuation=dict(Counter(re.findall(r'[，。！？：；、,.!?;:]', text))),
                mixing=dict(spaced=len(re.findall(r'[\u4e00-\u9fff] +[A-Za-z]|[A-Za-z] +[\u4e00-\u9fff]', text)),
                            adjacent=len(re.findall(r'[\u4e00-\u9fff][A-Za-z]|[A-Za-z][\u4e00-\u9fff]', text))),
                sentence_openers=Counter(s[:4] for s in sentences).most_common(10), phrases=phrases.most_common(10),
                colloquial_markers=len(re.findall(r'嘛|啦|吧|咱|这儿|挺|咋', text)), concise_proxy=bool(sentences) and mean < 35)
