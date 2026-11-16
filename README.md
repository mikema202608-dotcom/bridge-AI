# AI 学习空间

GitHub 保存代码并触发部署。云服务器运行网站，访客无需等待本地电脑开机。站长后台和视频数据继续由服务器管理。

1. 创建一个私有 GitHub 仓库，把本目录内容提交到 `main`（包括 `.github` 下的工作流）。
2. 在云服务器安装 Docker 和 Docker Compose v2。准备部署用的 SSH 用户，确保它可执行 Docker。用该用户创建 `~/ai-learning-studio`，在其中创建权限为 `600` 的 `.env`，参考 `.env.example` 填写真实域名和独立站长密码。
3. 把域名解析到服务器。开放 80、443，以及供 GitHub Actions 部署用的 SSH 端口（工作流使用默认 22）。
4. 在 GitHub 仓库的 Settings → Secrets and variables → Actions 中添加仓库变量 `DEPLOY_HOST`（IP 或主机名）、`DEPLOY_USER`（SSH 用户）和 `SITE_URL`（访客的完整 HTTPS 网址）。添加仓库机密 `DEPLOY_SSH_KEY`（专用于部署的 SSH 私钥）和 `DEPLOY_KNOWN_HOSTS`（从服务器控制台核对过指纹的 SSH 主机公钥记录）。把对应部署公钥加入服务器部署用户的 SSH 授权列表。
5. 在 Actions 页面运行「部署 AI 学习空间」。以后推送到 `main` 会重新部署。工作流会检查访客课程接口能否从公网通过 HTTPS 打开。

站长入口为 `/login`。上传的视频与课程目录位于服务器的 `courses` 数据卷。保持部署目录和 Compose 项目名一致，备份该数据卷。旧站课程不会自动迁移。把网址放进汇报前，用一部关闭 Wi-Fi 的手机试开并试播。
