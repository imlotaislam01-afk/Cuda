from brain.runtime import EngineSupervisor
from config.runtime import RuntimeConfig


def main() -> None:
    runtime = RuntimeConfig.from_env()
    supervisor = EngineSupervisor(config=runtime)
    started = supervisor.start()

    print()
    print("========================================")
    print("             APEX BRAIN v1")
    print("========================================")
    print(f"Runtime:       {runtime.mode.value}")
    print(f"Lifecycle:     {supervisor.state.value}")
    print(f"Started:       {started}")
    print(f"EXECUTE:       {supervisor.execution_allowed}")
    print("NOTE: Live execution is disabled.")
    print("========================================")
    print()

    supervisor.stop()


if __name__ == "__main__":
    main()
