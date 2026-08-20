#!/usr/bin/env bash
# cookGPT 一键部署到腾讯云(首次部署与日常更新通用)
#
# 用法:
#   SERVER=ubuntu@你的服务器IP ./deploy/deploy.sh
#
# 前置(只在首次需要):
#   1. 服务器已装好 uv(没装会自动装)
#   2. 服务器安全组放行 TCP 8000
#   3. 服务器上已有 /data/cookgpt 目录(向量库放持久盘):
#        ssh $SERVER "sudo mkdir -p /data/cookgpt && sudo chown -R \$(whoami) /data/cookgpt"
#   4. 服务器 .env 里 COOKGPT_MILVUS_DIR=/data/cookgpt/milvus(首次部署后手动改一次)
set -euo pipefail

SERVER=${SERVER:?请设置 SERVER=ubuntu@服务器IP,例如: SERVER=ubuntu@1.2.3.4 ./deploy/deploy.sh}
REMOTE_DIR=/opt/cookgpt

echo "== 1/5 本地构建前端 =="
(cd frontend && npm install --silent && npm run build)

echo "== 2/5 同步代码(含 .env)到服务器 =="
rsync -az --delete \
  --exclude .venv --exclude .git \
  --exclude frontend/node_modules --exclude frontend/dist \
  --exclude backend/data \
  ./ "$SERVER:$REMOTE_DIR/"

echo "== 3/5 同步前端产物与本地数据(向量库/用户库)=="
rsync -az frontend/dist/ "$SERVER:$REMOTE_DIR/frontend/dist/"
rsync -az backend/data/ "$SERVER:$REMOTE_DIR/backend/data/"

echo "== 4/5 服务器安装依赖 =="
ssh "$SERVER" "cd $REMOTE_DIR && \
  (command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh) && \
  export PATH=\"\$HOME/.local/bin:\$PATH\" && uv sync"

echo "== 5/5 安装/重启 systemd 服务 =="
ssh "$SERVER" "sudo cp $REMOTE_DIR/deploy/cookgpt.service /etc/systemd/system/ && \
  sudo systemctl daemon-reload && \
  sudo systemctl enable --now cookgpt && sleep 2 && \
  sudo systemctl status cookgpt --no-pager | head -10"

echo
echo "✓ 部署完成,访问 http://$(echo "$SERVER" | cut -d@ -f2):8000"
echo "  查看日志: ssh $SERVER 'sudo journalctl -u cookgpt -f'"
