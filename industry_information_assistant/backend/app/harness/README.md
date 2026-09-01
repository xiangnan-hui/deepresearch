# Research Harness

Harness 是 Deep Research 的外层运行时，LangGraph 仍是工作流编排器。

执行链路：

1. `ResearchHarness` 为每次任务创建不可变的 `RunContext`。
2. `RunContext` 携带运行 ID、当前时间、模型和时效性策略进入 Graph state。
3. LangGraph 负责节点、分支、循环以及 `custom stream`。
4. Agent 的模型请求统一经过 `ModelGateway`。
5. Tool/Skill 通过注册表声明；首个内置 Skill 是 `fresh_research`。
6. Graph 完成后运行确定性质量门，Harness 再把事件包装成稳定的 SSE 信封。

Harness 不包含研究步骤顺序，因此不会形成第二套工作流框架。
