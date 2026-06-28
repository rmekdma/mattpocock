# Matt Pocock Codex Skills

이 repo는 [mattpocock/skills](https://github.com/mattpocock/skills)를 Codex 용도로 변환한 결과물입니다.

- 사용한 source commit: [`5d78b`](https://github.com/mattpocock/skills/commit/5d78bd0903420f97c791f834201e550c765699f8)
- 원본 `skills/` 전체를 `skills/<bucket>/<skill>/` 구조 그대로 복사합니다.
- `.codex-plugin/plugin.json`의 노출 목록은 원본 `.claude-plugin/plugin.json`의 `skills` 배열에서 가져옵니다.
- 생성 및 업데이트는 [`update-from-source.py`](./update-from-source.py)를 사용합니다.

## Update

원본 repo가 업데이트되면 다음 명령으로 이 Codex용 출력물을 다시 생성합니다.

```bash
# 1. skills 없을 때
git clone https://github.com/mattpocock/skills.git
cd skills

# 2. skills 있을 때
cd skills
git pull

git clone https://github.com/rmekdma/mattpocock.git
./mattpocock/update-from-source.py
cp -r mattpocock ~/.agents/skills
```
