from core.application import LessanApplication
from core.kernel import AgentKernel
from core.kernel.component import KernelComponent


class Component(KernelComponent):
    name = "runtime-test"
    is_critical = True
    health_interval = 0

    def __init__(self):
        super().__init__()
        self.started_count = 0
        self.stopped_count = 0

    def start(self):
        self.started_count += 1

    def stop(self):
        self.stopped_count += 1


def test_application_start_and_shutdown_are_idempotent():
    component = Component()
    kernel = AgentKernel()
    kernel.register(component)
    app = LessanApplication(kernel=kernel)

    first = app.start()
    second = app.start()
    assert first is second
    assert component.started_count == 1

    app.shutdown()
    app.shutdown()
    assert component.stopped_count == 1
    assert kernel.status_name == "stopped"
