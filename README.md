# discocan

Hardware + host tooling for the **NSWE001** embedded-systems lab at Charles
University: an STM32F407 Discovery board reflashed as a USB↔CAN adapter and
2-axis punchpress simulator, plus a Python package that drives it.

## Repository layout

| Path                       | What's there                                                         |
|----------------------------|----------------------------------------------------------------------|
| [`firmware/`](firmware/)   | STM32CubeMX / CMake project for the adapter firmware (STM32F407).    |
| [`client/`](client/)       | Python package `discocan` — TUI, web UI, REST/WS server, CLI.        |

The host-side documentation — install, CLI usage, TUI hotkeys, full CAN
frame reference, USB framing, REST API — lives in [`client/README.md`](client/README.md).

The firmware is a standard STM32CubeMX project; open `firmware/discocan.ioc`
in CubeMX/CubeIDE, or build from `firmware/` with the supplied
`CMakePresets.json` and an `arm-none-eabi` toolchain.

## License

MIT — see [`firmware/LICENSE`](firmware/LICENSE) for the firmware (vendor
subtrees under `firmware/Drivers/` and `firmware/Middlewares/` keep their
own licenses) and the `license` field in [`client/pyproject.toml`](client/pyproject.toml)
for the host package.
