#!/usr/bin/env bash
# 커밋 위생(ARCHITECTURE 7절 · P1-02 ⑥): `origin/quant-service..HEAD`의 모든 커밋이
#   작성자 · 커미터 = 정확히 `Junsang Yoo <70479629+junsangyooo@users.noreply.github.com>` · 꼬리 줄 0 ·
#   메시지에 쓰지 않는 낱말(claude|co-authored|session_…|generated with|anthropic.com) 0
# 인지 봐요. 어느 폴더에서 불러도 같아요(이 파일 위치 기준). 종료 코드: 0 통과 · 1 어긋남 · 2 범위를 셀 수 없음.
set -u
cd "$(dirname "$0")/.." || exit 2
want='Junsang Yoo <70479629+junsangyooo@users.noreply.github.com>'
bad='claude|co-authored|session_[A-Za-z0-9]{20,}|generated with|anthropic\.com'
range=${1:-origin/quant-service..HEAD}
git rev-list "$range" >/dev/null 2>&1 || { echo "커밋 범위를 셀 수 없어요: $range (origin/quant-service를 fetch했는지 봐요)" >&2; exit 2; }
n=$(git rev-list --count "$range")
fail=0
# ARCHITECTURE 7절의 식 그대로: 모든 줄이 "$want / $want / "(꼬리 줄 자리 비어 있음)
git log --format='%h %an <%ae> / %cn <%ce> / %(trailers)' "$range" | sed '/^[[:space:]]*$/d' | while IFS= read -r line; do
  rest=${line#* }
  [ "$rest" = "$want / $want / " ] || echo "작성자 · 커미터 · 꼬리 줄이 어긋나요: $line"
done | tee /dev/stderr | grep -q . && fail=1
if git log --format=%B "$range" | grep -qiE "$bad"; then
  echo "커밋 메시지에 쓰지 않는 낱말이 있어요:" >&2
  git log --format='%h %s%n%b' "$range" | grep -inE "$bad" >&2
  fail=1
fi
if [ -n "$(git log --format='%(trailers:only)' "$range" | tr -d '[:space:]')" ]; then
  echo "꼬리 줄이 있는 커밋이 있어요:" >&2
  git log --format='%h %(trailers:only)' "$range" | sed '/^[0-9a-f]\{7,\}[[:space:]]*$/d' >&2
  fail=1
fi
echo "커밋 위생: $range 커밋 $n개 · 작성자 · 커미터 · 꼬리 줄 · 낱말 $([ "$fail" = 0 ] && echo 모두 통과 || echo 어긋남)"
exit "$fail"
