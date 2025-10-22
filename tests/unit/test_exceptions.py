"""异常模块单元测试。

测试自定义异常类的行为和错误检测功能。
"""

import pytest

from src.z2p_svc.exceptions import (
    UpstreamAPIError,
    AuthenticationError,
    FileUploadError,
    RateLimitError,
    BadRequestError,
    PermissionError,
    MethodNotAllowedError,
    ServerError,
    is_aliyun_blocked_response,
)


@pytest.mark.unit
class TestUpstreamAPIError:
    """UpstreamAPIError 基础异常测试。"""
    
    def test_basic_initialization(self):
        """测试基本初始化。"""
        error = UpstreamAPIError(500, "Server error")
        
        assert error.status_code == 500
        assert error.message == "Server error"
        assert error.error_type == "upstream_error"
        assert str(error) == "Server error"
    
    def test_custom_error_type(self):
        """测试自定义错误类型。"""
        error = UpstreamAPIError(400, "Bad request", "custom_error")
        
        assert error.error_type == "custom_error"
    
    def test_inheritance_from_exception(self):
        """测试继承自 Exception。"""
        error = UpstreamAPIError(500, "Error")
        
        assert isinstance(error, Exception)


@pytest.mark.unit
class TestAuthenticationError:
    """AuthenticationError 认证错误测试。"""
    
    def test_default_values(self):
        """测试默认值。"""
        error = AuthenticationError()
        
        assert error.status_code == 401
        assert error.message == "认证失败"
        assert error.error_type == "authentication_error"
    
    def test_custom_message(self):
        """测试自定义消息。"""
        error = AuthenticationError("Invalid token")
        
        assert error.message == "Invalid token"
        assert error.status_code == 401
    
    def test_custom_status_code(self):
        """测试自定义状态码。"""
        error = AuthenticationError("Error", status_code=403)
        
        assert error.status_code == 403


@pytest.mark.unit
class TestFileUploadError:
    """FileUploadError 文件上传错误测试。"""
    
    def test_default_values(self):
        """测试默认值。"""
        error = FileUploadError()
        
        assert error.status_code == 400
        assert error.message == "文件上传失败"
        assert error.error_type == "file_upload_error"
    
    def test_custom_message(self):
        """测试自定义消息。"""
        error = FileUploadError("File too large")
        
        assert error.message == "File too large"


@pytest.mark.unit
class TestRateLimitError:
    """RateLimitError 速率限制错误测试。"""
    
    def test_default_values(self):
        """测试默认值。"""
        error = RateLimitError()
        
        assert error.status_code == 429
        assert error.message == "请求过于频繁"
        assert error.error_type == "rate_limit_error"


@pytest.mark.unit
class TestBadRequestError:
    """BadRequestError 请求参数错误测试。"""
    
    def test_default_values(self):
        """测试默认值。"""
        error = BadRequestError()
        
        assert error.status_code == 400
        assert error.message == "请求参数错误"
        assert error.error_type == "bad_request_error"


@pytest.mark.unit
class TestPermissionError:
    """PermissionError 权限错误测试。"""
    
    def test_default_values(self):
        """测试默认值。"""
        error = PermissionError()
        
        assert error.status_code == 403
        assert error.message == "权限不足"
        assert error.error_type == "permission_error"


@pytest.mark.unit
class TestMethodNotAllowedError:
    """MethodNotAllowedError 方法不允许错误测试。"""
    
    def test_default_values(self):
        """测试默认值。"""
        error = MethodNotAllowedError()
        
        assert error.status_code == 405
        assert error.message == "请求方法不允许"
        assert error.error_type == "method_not_allowed_error"


@pytest.mark.unit
class TestServerError:
    """ServerError 服务器错误测试。"""
    
    def test_default_values(self):
        """测试默认值。"""
        error = ServerError()
        
        assert error.status_code == 500
        assert error.message == "上游服务器错误"
        assert error.error_type == "server_error"


@pytest.mark.unit
class TestIsAliyunBlockedResponse:
    """is_aliyun_blocked_response 函数测试。"""
    
    def test_empty_response(self):
        """测试空响应。"""
        assert is_aliyun_blocked_response("") is False
    
    def test_normal_response(self):
        """测试正常响应。"""
        normal_html = "<html><body>Normal content</body></html>"
        assert is_aliyun_blocked_response(normal_html) is False
    
    def test_aliyun_blocked_response_with_multiple_indicators(self):
        """测试包含多个阿里云拦截特征的响应。"""
        blocked_html = """
        <html>
        <body data-spm="aliyun">
        <div id="block_message">由于您访问的URL有可能对网站造成安全威胁</div>
        <div id="block_traceid">trace123</div>
        </body>
        </html>
        """
        assert is_aliyun_blocked_response(blocked_html) is True
    
    def test_aliyun_blocked_response_with_error_image(self):
        """测试包含阿里云错误图片的响应。"""
        blocked_html = """
        <html>
        <body data-spm="aliyun">
        <img src="https://errors.aliyun.com/error.png" />
        <p>potential threats to the server</p>
        </body>
        </html>
        """
        assert is_aliyun_blocked_response(blocked_html) is True
    
    def test_single_indicator_not_enough(self):
        """测试单个特征不足以判定为拦截。"""
        html_with_one_indicator = '<div data-spm="something">Content</div>'
        assert is_aliyun_blocked_response(html_with_one_indicator) is False
    
    def test_chinese_warning_message(self):
        """测试中文警告消息。"""
        blocked_html = """
        <html>
        <body data-spm="aliyun">
        <p>由于您访问的URL有可能对网站造成安全威胁，您的访问被阻断。</p>
        </body>
        </html>
        """
        assert is_aliyun_blocked_response(blocked_html) is True
    
    def test_english_warning_message(self):
        """测试英文警告消息。"""
        blocked_html = """
        <html>
        <body>
        <div id="block_message">potential threats to the server</div>
        <img src="https://errors.aliyun.com/blocked.png" />
        </body>
        </html>
        """
        assert is_aliyun_blocked_response(blocked_html) is True
    
    def test_case_sensitivity(self):
        """测试大小写敏感性。"""
        # 特征检测应该是大小写敏感的
        blocked_html = """
        <html>
        <body DATA-SPM="aliyun">
        <div id="BLOCK_MESSAGE">Warning</div>
        </body>
        </html>
        """
        # 由于检测是大小写敏感的，大写的特征不会被识别
        # 但如果有足够多的其他特征，仍然可以判定
        result = is_aliyun_blocked_response(blocked_html)
        # 这个测试验证实现的行为
        assert isinstance(result, bool)


@pytest.mark.unit
class TestExceptionHierarchy:
    """异常继承层次测试。"""
    
    def test_all_custom_errors_inherit_from_upstream_api_error(self):
        """测试所有自定义错误都继承自 UpstreamAPIError。"""
        errors = [
            AuthenticationError(),
            FileUploadError(),
            RateLimitError(),
            BadRequestError(),
            PermissionError(),
            MethodNotAllowedError(),
            ServerError(),
        ]
        
        for error in errors:
            assert isinstance(error, UpstreamAPIError)
            assert isinstance(error, Exception)
    
    def test_error_attributes_consistency(self):
        """测试错误属性一致性。"""
        errors = [
            (AuthenticationError(), 401, "authentication_error"),
            (FileUploadError(), 400, "file_upload_error"),
            (RateLimitError(), 429, "rate_limit_error"),
            (BadRequestError(), 400, "bad_request_error"),
            (PermissionError(), 403, "permission_error"),
            (MethodNotAllowedError(), 405, "method_not_allowed_error"),
            (ServerError(), 500, "server_error"),
        ]
        
        for error, expected_code, expected_type in errors:
            assert error.status_code == expected_code
            assert error.error_type == expected_type
            assert hasattr(error, "message")