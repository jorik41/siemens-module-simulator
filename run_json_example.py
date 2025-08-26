from plan_runner import run_json_plan


def main() -> None:
    run_json_plan("json_plan_example.json", ip="127.0.0.1", rack=0, slot=1)


if __name__ == "__main__":
    main()
