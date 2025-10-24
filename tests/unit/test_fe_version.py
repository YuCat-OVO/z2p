"""FE版本自动获取模块单元测试。

测试 fe_version 模块的核心功能，包括版本提取、缓存、后台更新等。
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch

from src.z2p_svc.fe_version import (
    _extract_version,
    initialize_fe_version,
    update_fe_version,
    get_cached_version,
    start_background_update,
    stop_background_update,
)


@pytest.mark.unit
class TestExtractVersion:
    """_extract_version 函数测试。"""

    def test_extract_single_version(self):
        """测试提取单个版本号。"""
        content = '<script src="/static/prod-fe-1.0.108/main.js"></script>'
        result = _extract_version(content)
        assert result == "prod-fe-1.0.108"

    def test_extract_multiple_versions(self):
        """测试提取多个版本号时返回最高版本。"""
        content = """
        <script src="/static/prod-fe-1.0.108/main.js"></script>
        <link href="/static/prod-fe-1.0.110/style.css">
        <script src="/static/prod-fe-1.0.109/app.js"></script>
        """
        result = _extract_version(content)
        assert result == "prod-fe-1.0.110"

    def test_no_version_found(self):
        """测试未找到版本号。"""
        content = "<html><body>No version here</body></html>"
        result = _extract_version(content)
        assert result is None

    def test_empty_content(self):
        """测试空内容。"""
        result = _extract_version("")
        assert result is None

    def test_none_content(self):
        """测试 None 内容。"""
        result = _extract_version(None)  # type: ignore
        assert result is None

    def test_version_pattern_variations(self):
        """测试不同的版本号格式。"""
        test_cases = [
            ("prod-fe-1.0.1", "prod-fe-1.0.1"),
            ("prod-fe-10.20.300", "prod-fe-10.20.300"),
            ("prod-fe-0.0.0", "prod-fe-0.0.0"),
        ]
        for content, expected in test_cases:
            result = _extract_version(content)
            assert result == expected


@pytest.mark.unit
class TestInitializeFEVersion:
    """initialize_fe_version 函数测试。"""

    @pytest.mark.asyncio
    async def test_successful_initialization(self):
        """测试成功初始化。"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<script src="/static/prod-fe-1.0.120/main.js"></script>'

        with patch("src.z2p_svc.fe_version.AsyncSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await initialize_fe_version("chrome136", "prod-fe-1.0.100")

            assert result == "prod-fe-1.0.120"
            assert get_cached_version() == "prod-fe-1.0.120"

    @pytest.mark.asyncio
    async def test_initialization_with_fallback(self):
        """测试初始化失败时使用降级值。"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html>No version</html>"

        with patch("src.z2p_svc.fe_version.AsyncSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await initialize_fe_version("chrome136", "prod-fe-1.0.100")

            assert result == "prod-fe-1.0.100"
            assert get_cached_version() == "prod-fe-1.0.100"

    @pytest.mark.asyncio
    async def test_initialization_network_error(self):
        """测试网络错误时使用降级值。"""
        with patch("src.z2p_svc.fe_version.AsyncSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(side_effect=Exception("Network error"))
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await initialize_fe_version("chrome136", "prod-fe-1.0.100")

            assert result == "prod-fe-1.0.100"

    @pytest.mark.asyncio
    async def test_initialization_http_error(self):
        """测试 HTTP 错误时使用降级值。"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("src.z2p_svc.fe_version.AsyncSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await initialize_fe_version("chrome136", "prod-fe-1.0.100")

            assert result == "prod-fe-1.0.100"


@pytest.mark.unit
class TestUpdateFEVersion:
    """update_fe_version 函数测试。"""

    @pytest.mark.asyncio
    async def test_successful_update(self):
        """测试成功更新版本。"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<script src="/static/prod-fe-1.0.125/main.js"></script>'

        with patch("src.z2p_svc.fe_version.AsyncSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await update_fe_version("chrome136")

            assert result == "prod-fe-1.0.125"
            assert get_cached_version() == "prod-fe-1.0.125"

    @pytest.mark.asyncio
    async def test_update_failure(self):
        """测试更新失败。"""
        with patch("src.z2p_svc.fe_version.AsyncSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(side_effect=Exception("Connection failed"))
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await update_fe_version("chrome136")

            assert result is None

    @pytest.mark.asyncio
    async def test_update_no_version_found(self):
        """测试更新时未找到版本号。"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html>No version</html>"

        with patch("src.z2p_svc.fe_version.AsyncSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await update_fe_version("chrome136")

            assert result is None


@pytest.mark.unit
class TestGetCachedVersion:
    """get_cached_version 函数测试。"""

    @pytest.mark.asyncio
    async def test_get_cached_version_after_init(self):
        """测试初始化后获取缓存版本。"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<script src="/static/prod-fe-1.0.130/main.js"></script>'

        with patch("src.z2p_svc.fe_version.AsyncSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            await initialize_fe_version("chrome136", "prod-fe-1.0.100")
            cached = get_cached_version()

            assert cached == "prod-fe-1.0.130"


@pytest.mark.unit
class TestBackgroundUpdate:
    """后台更新任务测试。"""

    @pytest.mark.asyncio
    async def test_start_background_update(self):
        """测试启动后台更新任务。"""
        mock_browser_func = Mock(return_value="chrome136")
        
        # 启动任务
        start_background_update(mock_browser_func)
        
        # 验证任务已创建
        from src.z2p_svc.fe_version import _update_task
        assert _update_task is not None
        assert not _update_task.done()
        
        # 清理
        stop_background_update()
        await asyncio.sleep(0.1)  # 等待任务取消

    @pytest.mark.asyncio
    async def test_stop_background_update(self):
        """测试停止后台更新任务。"""
        mock_browser_func = Mock(return_value="chrome136")
        
        # 启动任务
        start_background_update(mock_browser_func)
        
        # 停止任务
        stop_background_update()
        await asyncio.sleep(0.1)  # 等待任务取消
        
        # 验证任务已取消
        from src.z2p_svc.fe_version import _update_task
        assert _update_task is not None
        assert _update_task.cancelled() or _update_task.done()

    @pytest.mark.asyncio
    async def test_start_multiple_times(self):
        """测试多次启动不会创建多个任务。"""
        mock_browser_func = Mock(return_value="chrome136")
        
        # 第一次启动
        start_background_update(mock_browser_func)
        from src.z2p_svc.fe_version import _update_task
        first_task = _update_task
        
        # 第二次启动（任务仍在运行）
        start_background_update(mock_browser_func)
        second_task = _update_task
        
        # 应该是同一个任务
        assert first_task is second_task
        
        # 清理
        stop_background_update()
        await asyncio.sleep(0.1)  # 等待任务取消

    @pytest.mark.asyncio
    async def test_restart_after_stop(self):
        """测试停止后可以重新启动。"""
        mock_browser_func = Mock(return_value="chrome136")
        
        # 启动并停止
        start_background_update(mock_browser_func)
        stop_background_update()
        await asyncio.sleep(0.1)  # 等待任务取消
        
        # 重新启动
        start_background_update(mock_browser_func)
        from src.z2p_svc.fe_version import _update_task
        assert _update_task is not None
        assert not _update_task.done()
        
        # 清理
        stop_background_update()
        await asyncio.sleep(0.1)  # 等待任务取消


@pytest.mark.unit
class TestBrowserVersionIntegration:
    """浏览器版本集成测试。"""

    @pytest.mark.asyncio
    async def test_different_browser_versions(self):
        """测试不同浏览器版本的请求。"""
        browser_versions = ["chrome136", "safari260", "firefox133"]
        
        for browser_version in browser_versions:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = '<script src="/static/prod-fe-1.0.140/main.js"></script>'

            with patch("src.z2p_svc.fe_version.AsyncSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session.get = AsyncMock(return_value=mock_response)
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=None)
                mock_session_class.return_value = mock_session

                result = await initialize_fe_version(browser_version, "prod-fe-1.0.100")

                assert result == "prod-fe-1.0.140"
                # 验证使用了正确的浏览器版本
                mock_session_class.assert_called_with(impersonate=browser_version)


@pytest.mark.unit
class TestEdgeCases:
    """边缘情况测试。"""

    @pytest.mark.asyncio
    async def test_malformed_html(self):
        """测试格式错误的 HTML。"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html><script>prod-fe-1.0.150</script"  # 缺少闭合标签

        with patch("src.z2p_svc.fe_version.AsyncSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await initialize_fe_version("chrome136", "prod-fe-1.0.100")

            # 应该能提取到版本号
            assert result == "prod-fe-1.0.150"

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """测试超时处理。"""
        with patch("src.z2p_svc.fe_version.AsyncSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(side_effect=asyncio.TimeoutError("Timeout"))
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await initialize_fe_version("chrome136", "prod-fe-1.0.100")

            # 应该使用降级值
            assert result == "prod-fe-1.0.100"

    @pytest.mark.asyncio
    async def test_empty_fallback(self):
        """测试空降级值。"""
        with patch("src.z2p_svc.fe_version.AsyncSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(side_effect=Exception("Error"))
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await initialize_fe_version("chrome136", "")

            # 应该返回空字符串
            assert result == ""

    def test_version_comparison_logic(self):
        """测试版本号比较逻辑（字典序）。"""
        content = """
        prod-fe-1.0.9
        prod-fe-1.0.10
        prod-fe-1.0.100
        """
        result = _extract_version(content)
        # 字典序最大的是 "prod-fe-1.0.9"（不是数值最大）
        assert result == "prod-fe-1.0.9"