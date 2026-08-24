#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞牛 fnOS Docker Compose → .fpk 打包工具 - WebUI 版
改为固定目录生成，避免临时目录问题
"""

import os
import shutil
import subprocess
import zipfile
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
import streamlit as st
from PIL import Image
import io

st.set_page_config(
    page_title="飞牛 fnOS 打包工具",
    page_icon="📦",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 固定输出目录（在当前工作目录下）
OUTPUT_ROOT = Path(os.environ.get("OUTPUT_ROOT", "fnos_output")).resolve()


def find_fnpack() -> Optional[str]:
    # 优先使用环境变量指定的路径（Docker 部署）
    env_path = os.environ.get("FNPACK_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    candidates = [
        "fnpack",
        "./fnpack",
        "./fnpack.exe",
        "/usr/local/bin/fnpack",
        "/data/fnpack/fnpack",
        str(Path.home() / "fnpack"),
        r"C:\fnpack\fnpack.exe",
        str(Path.cwd() / "fnpack.exe"),
    ]
    for c in candidates:
        if shutil.which(c) or Path(c).exists():
            return str(Path(c).resolve()) if Path(c).exists() else c
    for p in Path(".").glob("fnpack*"):
        if p.is_file():
            return str(p.resolve())
    return None


def process_icon(img: Image.Image, dest_dir: Path) -> bool:
    try:
        if img.mode in ("P", "LA"):
            img = img.convert("RGBA")
        elif img.mode != "RGBA":
            img = img.convert("RGBA")

        resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS

        def make_icon(size: int, filename: str, target_dir: Path):
            icon = img.copy()
            icon.thumbnail((size, size), resample)
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            offset = ((size - icon.width) // 2, (size - icon.height) // 2)
            canvas.paste(icon, offset, icon if icon.mode == "RGBA" else None)
            target_dir.mkdir(parents=True, exist_ok=True)
            canvas.save(target_dir / filename, format="PNG", optimize=True)

        # 根目录图标（必须）
        make_icon(64, "ICON.PNG", dest_dir)
        make_icon(256, "ICON_256.PNG", dest_dir)

        # app/ui/images/ 图标
        ui_images = dest_dir / "app" / "ui" / "images"
        make_icon(64, "icon_64.png", ui_images)
        make_icon(256, "icon_256.png", ui_images)
        return True
    except Exception as e:
        st.error(f"图标处理失败: {e}")
        return False


def create_project_structure(
    base: Path,
    info: Dict[str, Any],
    compose_content: str,
    with_ui: bool,
    icon_img: Optional[Image.Image]
):
    app_name = info["appname"]
    launch_name = f"{app_name}.main"

    # 清理旧目录
    if base.exists():
        shutil.rmtree(base)
    (base / "app" / "docker").mkdir(parents=True, exist_ok=True)
    (base / "cmd").mkdir(parents=True, exist_ok=True)
    (base / "config").mkdir(parents=True, exist_ok=True)

    # 1. docker-compose.yaml
    (base / "app" / "docker" / "docker-compose.yaml").write_text(
        compose_content,
        encoding="utf-8"
    )

    # 2. manifest
    manifest_lines = [
        f"appname={app_name}",
        f"version={info['version']}",
        f"display_name={info['display_name']}",
        f"desc={info['desc']}",
        "platform=x86",
        "source=thirdparty",
        f"maintainer={info['maintainer']}",
        f"maintainer_url={info.get('maintainer_url', '')}",
        f"distributor={info.get('distributor', info['maintainer'])}",
        f"distributor_url={info.get('distributor_url', '')}",
        f"helpurl={info.get('helpurl', '')}",
        "os_min_version=1.1.8",
        f"service_port={info['service_port']}",
    ]
    if with_ui:
        manifest_lines.append("desktop_uidir=ui")
        manifest_lines.append(f"desktop_applaunchname={launch_name}")

    (base / "manifest").write_text(
        "\n".join(manifest_lines) + "\n",
        encoding="utf-8"
    )

    # 3. privilege & resource
    (base / "config" / "privilege").write_text(
        """{
  "defaults": {
    "run-as": "root"
  }
}
""",
        encoding="utf-8"
    )

    resource = {
        "docker-project": {
            "projects": [
                {
                    "name": app_name,
                    "path": "docker"
                }
            ]
        }
    }
    (base / "config" / "resource").write_text(
        json.dumps(resource, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 4. cmd 脚本
    # Docker Compose 项目的生命周期由 fnOS Docker Project 管理。
    # 这里仅提供状态检查，避免重复执行 docker compose up/down。
    main_script = r'''#!/bin/bash

FILE_PATH="${TRIM_APPDEST}/docker/docker-compose.yaml"

is_docker_running() {
    DOCKER_NAME=""

    if [ -f "$FILE_PATH" ]; then
        DOCKER_NAME=$(grep "container_name" "$FILE_PATH" | head -n 1 | awk -F ':' '{print $2}' | xargs)
    fi

    if [ -n "$DOCKER_NAME" ]; then
        docker inspect "$DOCKER_NAME" 2>/dev/null |
            grep -q '"Status": "running",'
        return $?
    fi

    # 如果 compose 中没有 container_name，则回退到 compose ps。
    if command -v docker >/dev/null 2>&1; then
        PROJECT_DIR="${TRIM_APPDEST}/docker"
        if [ -d "$PROJECT_DIR" ]; then
            cd "$PROJECT_DIR" || return 1
            docker compose ps --status running --format '{{.Name}}' 2>/dev/null | grep -q .
            return $?
        fi
    fi

    return 1
}

case "$1" in
    start)
        exit 0
        ;;
    stop)
        exit 0
        ;;
    status)
        if is_docker_running; then
            exit 0
        else
            exit 3
        fi
        ;;
    *)
        exit 1
        ;;
esac
'''
    main_path = base / "cmd" / "main"
    main_path.write_text(main_script, encoding="utf-8")
    try:
        main_path.chmod(0o755)
    except Exception:
        pass

    for name in [
        "install_init", "install_callback",
        "upgrade_init", "upgrade_callback",
        "uninstall_init", "uninstall_callback",
        "config_init", "config_callback"
    ]:
        p = base / "cmd" / name
        p.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        try:
            p.chmod(0o755)
        except Exception:
            pass

    # 5. UI config（严格按官方模板）
    if with_ui:
        (base / "app" / "ui" / "images").mkdir(parents=True, exist_ok=True)

        ui_config = {
            ".url": {
                launch_name: {
                    "title": info["display_name"],
                    "icon": "images/icon_{0}.png",
                    "type": "url",
                    "protocol": "http",
                    "port": str(info["service_port"]),
                    "url": "/",
                    "allUsers": False
                }
            }
        }
        (base / "app" / "ui" / "config").write_text(
            json.dumps(ui_config, ensure_ascii=False, indent=4),
            encoding="utf-8"
        )

    # 6. 图标
    if icon_img:
        process_icon(icon_img, base)
    else:
        # 创建有效 PNG，避免空文件导致问题
        from PIL import Image as PILImage
        tiny = PILImage.new("RGBA", (64, 64), (0, 0, 0, 0))
        tiny.save(base / "ICON.PNG", format="PNG")
        tiny2 = PILImage.new("RGBA", (256, 256), (0, 0, 0, 0))
        tiny2.save(base / "ICON_256.PNG", format="PNG")
        if with_ui:
            ui_images = base / "app" / "ui" / "images"
            ui_images.mkdir(parents=True, exist_ok=True)
            tiny.save(ui_images / "icon_64.png", format="PNG")
            tiny2.save(ui_images / "icon_256.png", format="PNG")


def make_zip(src_dir: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(src_dir):
            for file in files:
                full = Path(root) / file
                arcname = full.relative_to(src_dir)
                zf.write(full, arcname)
    buf.seek(0)
    return buf.getvalue()


def find_fpk_files(search_dirs: List[Path], appname: str) -> List[Path]:
    results = []
    patterns = [f"{appname}*.fpk", f"*{appname}*.fpk", "*.fpk"]
    for d in search_dirs:
        if not d.exists():
            continue
        for pattern in patterns:
            results.extend(list(d.glob(pattern)))
            results.extend(list(d.rglob(pattern)))
    unique = list({str(p.resolve()): p for p in results}.values())
    return unique


# ==================== 页面 ====================

st.header("📦 飞牛 fnOS Docker Compose → .fpk 打包工具")
st.caption("固定目录生成，避免临时目录问题 · 支持拖拽上传 docker-compose + 图标一键打包")

st.info(
    """
    **使用前请先下载 fnpack 打包工具**  
    官方下载与说明：[https://developer.fnnas.com/docs/cli/fnpack/](https://developer.fnnas.com/docs/cli/fnpack/)

    - **Linux x86**：`fnpack-*-linux-amd64`
    - **Linux ARM**：`fnpack-*-linux-arm64`
    - Windows / macOS 版本仅用于本机，**Docker 容器内必须使用 Linux 版**
    - 下载后放到宿主机 `./data/fnpack/` 目录（或设置环境变量 `FNPACK_PATH`）
    """,
    icon="📦"
)

st.divider()

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1️⃣ 上传文件")
    compose_file = st.file_uploader("拖拽上传 docker-compose.yml", type=["yml", "yaml"])
    icon_file = st.file_uploader("拖拽上传应用图标（推荐）", type=["png", "jpg", "jpeg", "webp", "bmp", "gif"])

with col2:
    st.subheader("2️⃣ 应用信息")
    appname = st.text_input("应用标识 (appname)", value="myapp")
    display_name = st.text_input("显示名称", value="我的应用")
    version = st.text_input("版本号 (X.Y.Z)", value="1.0.0")
    service_port = st.text_input("主要服务端口", value="8080")
    desc = st.text_area("应用描述", value="Docker 应用")
    maintainer = st.text_input("维护者", value="me")
    with_ui = st.checkbox("生成桌面图标入口", value=True)

st.divider()

with st.expander("高级选项"):
    maintainer_url = st.text_input("维护者网址", value="")
    distributor = st.text_input("分发者", value="")
    distributor_url = st.text_input("分发者网址", value="")
    helpurl = st.text_input("帮助文档网址", value="")
    try_build = st.checkbox("尝试用 fnpack 自动打包", value=True)

generate_btn = st.button("🚀 开始生成", type="primary", use_container_width=True)

if generate_btn:
    if not compose_file:
        st.error("请先上传 docker-compose.yml！")
        st.stop()

    if not appname or not appname.replace("_", "").isalnum() or not appname[0].isalpha():
        st.error("appname 格式不正确")
        st.stop()

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    base = OUTPUT_ROOT / appname

    with st.spinner("正在生成项目结构到固定目录..."):
        compose_content = compose_file.getvalue().decode("utf-8")

        icon_img = None
        if icon_file:
            try:
                icon_img = Image.open(icon_file)
            except Exception as e:
                st.warning(f"图标读取失败: {e}")

        info = {
            "appname": appname,
            "display_name": display_name,
            "version": version,
            "service_port": service_port,
            "desc": desc,
            "maintainer": maintainer,
            "maintainer_url": maintainer_url,
            "distributor": distributor or maintainer,
            "distributor_url": distributor_url,
            "helpurl": helpurl,
        }

        create_project_structure(base, info, compose_content, with_ui, icon_img)

        st.success(f"项目已生成到固定目录：`{base}`")
        st.info("你可以直接打开这个文件夹检查文件内容")

        project_zip = make_zip(base)

        fpk_bytes = None
        fpk_name = None

        if try_build:
            fnpack = find_fnpack()
            if fnpack:
                st.info(f"检测到 fnpack: `{fnpack}`")
                st.info(f"正在目录 `{base}` 中执行打包...")

                try:
                    # 关键：在项目目录里执行
                    result = subprocess.run(
                        [fnpack, "build"],
                        capture_output=True,
                        text=True,
                        cwd=str(base),
                        timeout=180
                    )

                    with st.expander("fnpack 完整输出", expanded=True):
                        st.code(result.stdout or "(无 stdout)")
                        if result.stderr:
                            st.code(result.stderr)

                    if result.returncode == 0:
                        # 在多个位置找 fpk
                        search_dirs = [
                            base,
                            base.parent,
                            Path.cwd(),
                            OUTPUT_ROOT,
                        ]
                        found = find_fpk_files(search_dirs, appname)

                        if found:
                            found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                            fpk_path = found[0]
                            fpk_bytes = fpk_path.read_bytes()
                            fpk_name = fpk_path.name
                            st.success(f"✅ 找到 .fpk：`{fpk_path}`")
                        else:
                            st.warning("fnpack 成功但未找到 .fpk 文件，请到下面目录手动查找：")
                            st.code(str(base))
                    else:
                        st.error(f"打包失败，退出码: {result.returncode}")
                except Exception as e:
                    st.error(f"执行出错: {e}")
            else:
                st.warning("未找到 fnpack，请手动进入项目目录执行打包")

        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            st.download_button(
                "⬇️ 下载项目结构 (zip)",
                data=project_zip,
                file_name=f"{appname}_project.zip",
                mime="application/zip",
                use_container_width=True
            )
        with col_b:
            if fpk_bytes:
                st.download_button(
                    "⬇️ 下载 .fpk 安装包",
                    data=fpk_bytes,
                    file_name=fpk_name or f"{appname}_{version}.fpk",
                    mime="application/octet-stream",
                    use_container_width=True
                )
            else:
                st.info("未生成 .fpk，请手动打包")

        st.markdown("### 手动打包方法（如果自动失败）")
        st.markdown(f"1. 打开文件夹：`{base}`")
        st.markdown("2. 在该文件夹打开 CMD，执行：")
        st.code("fnpack build", language="bash")
        st.markdown("3. 生成的 `.fpk` 会在当前目录或上级目录")
