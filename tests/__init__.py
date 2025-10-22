"""Z2P Chat Service 测试套件。

本包包含完整的测试套件，遵循逆向工程学习项目的最佳实践。

测试分层：
- unit/: 单元测试（80%）- 快速、隔离、完全 mock
- integration/: 集成测试（15%）- 组件协作、部分 mock
- system/: 系统测试（5%）- 端到端、需要授权

使用方法：
    pytest                          # 运行所有测试
    pytest tests/unit/ -m unit      # 仅单元测试
    pytest --cov=src/z2p_svc        # 生成覆盖率报告

详细文档：
- tests/README.md - 使用指南
- tests/TESTING_STRATEGY.md - 测试策略
"""

__version__ = "0"