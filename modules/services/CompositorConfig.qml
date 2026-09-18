import QtQuick
import Quickshell
import Quickshell.Io
import qs.modules.services
import qs.config
import qs.modules.theme
import qs.modules.bar
import qs.modules.globals

QtObject {
    id: root

    property Process compositorProcess: Process {}

    // Debounce: config changes arrive in bursts (a file reload touches dozens of
    // keys, each firing its own change signal). Everything funnels through this
    // timer so a burst results in exactly ONE process write, not dozens.
    property Timer applyTimer: Timer {
        interval: 100
        repeat: false
        onTriggered: applyCompositorConfigInternal()
    }

    function getColorValue(colorName) {
        const resolved = Config.resolveColor(colorName);
        // Convert HEX string to color, or return if already a color.
        return (typeof resolved === 'string') ? Qt.color(resolved) : resolved;
    }

    function formatColorForCompositor(color) {
        const r = Math.round(color.r * 255).toString(16).padStart(2, '0');
        const g = Math.round(color.g * 255).toString(16).padStart(2, '0');
        const b = Math.round(color.b * 255).toString(16).padStart(2, '0');
        const a = Math.round(color.a * 255).toString(16).padStart(2, '0');

        if (color.a === 1.0) {
            return `rgb(${r}${g}${b})`;
        }
        return `rgba(${r}${g}${b}${a})`;
    }

    // Lua literal for a JS value. Used to build hl.config({...}) for
    // `axctl config raw-batch "eval ..."`.
    function luaLiteral(value) {
        if (value === null || value === undefined)
            return "nil";
        const t = typeof value;
        if (t === "string")
            return JSON.stringify(value);
        if (t === "number")
            return isFinite(value) ? String(value) : "nil";
        if (t === "boolean")
            return value ? "true" : "false";
        if (Array.isArray(value))
            return "{" + value.map(luaLiteral).join(", ") + "}";
        if (t === "object") {
            const parts = [];
            for (const key in value) {
                if (!Object.prototype.hasOwnProperty.call(value, key))
                    continue;
                if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key))
                    continue;
                parts.push(key + " = " + luaLiteral(value[key]));
            }
            return "{" + parts.join(", ") + "}";
        }
        return "nil";
    }

    function formatBorderColorValue(colorNames, angle, fallbackName) {
        if (colorNames && colorNames.length > 1) {
            return {
                colors: colorNames.map(n => formatColorForCompositor(getColorValue(n))),
                angle: angle
            };
        }
        const singleName = (colorNames && colorNames.length === 1) ? colorNames[0] : fallbackName;
        return formatColorForCompositor(getColorValue(singleName));
    }

    function dispatchHlConfig(hlConfig) {
        const luaExpression = "hl.config(" + luaLiteral(hlConfig) + ")";
        compositorProcess.command = ["axctl", "config", "raw-batch", "eval " + luaExpression];
        compositorProcess.running = true;
    }

    function applyCompositorConfig() {
        applyTimer.restart();
    }

    function applyCompositorConfigInternal() {
        // Ensure adapters are loaded before applying config.
        if (!Config.loader.loaded) {
            return;
        }

        // Wait for layout to be ready.
        if (!GlobalStates.compositorLayoutReady) {
            return;
        }

        // Persist through TOML even while Game Mode holds the live compositor.
        if (GameModeService.toggled) {
            CompositorTomlWriter.refresh();
            return;
        }

        const c = Config.compositor;
        const borderColors = c.syncBorderColor ? null : c.activeBorderColor;
        const shadowBase = getColorValue(Config.compositorShadowColor);
        const shadowInactive = getColorValue(c.shadowColorInactive);
        const shadowOpacity = c.shadowOpacity !== undefined ? c.shadowOpacity : Config.compositorShadowOpacity;

        const hlGeneral = {
            gaps_in: c.gapsIn,
            gaps_out: c.gapsOut,
            border_size: Config.compositorBorderSize,
            col: {
                active_border: formatBorderColorValue(borderColors, c.borderAngle, Config.compositorBorderColor),
                inactive_border: formatBorderColorValue(c.inactiveBorderColor, c.inactiveBorderAngle, "surface")
            }
        };
        if (GlobalStates.compositorLayout)
            hlGeneral.layout = GlobalStates.compositorLayout;

        dispatchHlConfig({
            general: hlGeneral,
            decoration: {
                rounding: Config.compositorRounding,
                active_opacity: c.activeOpacity !== undefined ? c.activeOpacity : 1.0,
                inactive_opacity: c.inactiveOpacity !== undefined ? c.inactiveOpacity : 1.0,
                shadow: {
                    enabled: c.shadowEnabled,
                    range: c.shadowRange,
                    render_power: c.shadowRenderPower,
                    sharp: c.shadowSharp,
                    color: formatColorForCompositor(Qt.rgba(shadowBase.r, shadowBase.g, shadowBase.b, shadowBase.a * shadowOpacity)),
                    color_inactive: formatColorForCompositor(Qt.rgba(shadowInactive.r, shadowInactive.g, shadowInactive.b, shadowInactive.a * shadowOpacity)),
                    offset: c.shadowOffset || "0 0",
                    scale: c.shadowScale !== undefined ? c.shadowScale : 1.0
                },
                blur: {
                    enabled: c.blurEnabled,
                    size: c.blurSize,
                    passes: c.blurPasses,
                    ignore_opacity: c.blurIgnoreOpacity,
                    new_optimizations: c.blurNewOptimizations,
                    xray: c.blurXray,
                    noise: c.blurNoise,
                    contrast: c.blurContrast,
                    brightness: c.blurBrightness,
                    vibrancy: c.blurVibrancy,
                    vibrancy_darkness: c.blurVibrancyDarkness,
                    special: c.blurSpecial,
                    popups: c.blurPopups,
                    popups_ignorealpha: c.blurPopupsIgnorealpha,
                    input_methods: c.blurInputMethods,
                    input_methods_ignorealpha: c.blurInputMethodsIgnorealpha
                }
            }
        });

        CompositorTomlWriter.refresh();
    }

    property Connections gameModeConnections: Connections {
        target: GameModeService
        function onToggledChanged() {
            if (!GameModeService.toggled)
                applyCompositorConfig();
        }
    }

    property Connections configConnections: Connections {
        target: Config.loader
        function onFileChanged() {
            applyCompositorConfig();
        }
        function onLoaded() {
            applyCompositorConfig();
        }
    }

    property Connections compositorConfigConnections: Connections {
        target: Config.compositor

        function onBorderSizeChanged() {
            applyCompositorConfig();
        }
        function onRoundingChanged() {
            applyCompositorConfig();
        }
        function onGapsInChanged() {
            applyCompositorConfig();
        }
        function onGapsOutChanged() {
            applyCompositorConfig();
        }
        function onActiveBorderColorChanged() {
            applyCompositorConfig();
        }
        function onInactiveBorderColorChanged() {
            applyCompositorConfig();
        }
        function onBorderAngleChanged() {
            applyCompositorConfig();
        }
        function onInactiveBorderAngleChanged() {
            applyCompositorConfig();
        }
        function onSyncRoundnessChanged() {
            applyCompositorConfig();
        }
        function onSyncBorderWidthChanged() {
            applyCompositorConfig();
        }
        function onSyncBorderColorChanged() {
            applyCompositorConfig();
        }
        function onSyncShadowOpacityChanged() {
            applyCompositorConfig();
        }
        function onSyncShadowColorChanged() {
            applyCompositorConfig();
        }
        function onShadowEnabledChanged() {
            applyCompositorConfig();
        }
        function onShadowRangeChanged() {
            applyCompositorConfig();
        }
        function onShadowRenderPowerChanged() {
            applyCompositorConfig();
        }
        function onShadowSharpChanged() {
            applyCompositorConfig();
        }
        function onShadowIgnoreWindowChanged() {
            applyCompositorConfig();
        }
        function onShadowColorChanged() {
            applyCompositorConfig();
        }
        function onShadowColorInactiveChanged() {
            applyCompositorConfig();
        }
        function onShadowOpacityChanged() {
            applyCompositorConfig();
        }
        function onShadowOffsetChanged() {
            applyCompositorConfig();
        }
        function onShadowScaleChanged() {
            applyCompositorConfig();
        }
        function onBlurEnabledChanged() {
            applyCompositorConfig();
        }
        function onBlurSizeChanged() {
            applyCompositorConfig();
        }
        function onBlurPassesChanged() {
            applyCompositorConfig();
        }
        function onBlurIgnoreOpacityChanged() {
            applyCompositorConfig();
        }
        function onBlurExplicitIgnoreAlphaChanged() {
            applyCompositorConfig();
        }
        function onBlurIgnoreAlphaValueChanged() {
            applyCompositorConfig();
        }
        function onBlurNewOptimizationsChanged() {
            applyCompositorConfig();
        }
        function onBlurXrayChanged() {
            applyCompositorConfig();
        }
        function onBlurNoiseChanged() {
            applyCompositorConfig();
        }
        function onBlurContrastChanged() {
            applyCompositorConfig();
        }
        function onBlurBrightnessChanged() {
            applyCompositorConfig();
        }
        function onBlurVibrancyChanged() {
            applyCompositorConfig();
        }
        function onBlurVibrancyDarknessChanged() {
            applyCompositorConfig();
        }
        function onBlurSpecialChanged() {
            applyCompositorConfig();
        }
        function onBlurPopupsChanged() {
            applyCompositorConfig();
        }
        function onBlurPopupsIgnorealphaChanged() {
            applyCompositorConfig();
        }
        function onBlurInputMethodsChanged() {
            applyCompositorConfig();
        }
        function onBlurInputMethodsIgnorealphaChanged() {
            applyCompositorConfig();
        }
    }

    property Connections colorsConnections: Connections {
        target: Colors
        function onFileChanged() {
            applyCompositorConfig();
        }
        function onLoaded() {
            applyCompositorConfig();
        }
    }

    property Connections barConnections: Connections {
        target: Config.bar
        function onPositionChanged() {
            applyCompositorConfig();
        }
    }

    property Connections srBgConnections: Connections {
        target: Config.theme.srBg
        function onOpacityChanged() {
            applyCompositorConfig();
        }
    }

    property Connections srBarBgConnections: Connections {
        target: Config.theme.srBarBg
        function onOpacityChanged() {
            applyCompositorConfig();
        }
    }

    property Connections globalStatesConnections: Connections {
        target: GlobalStates
        function onCompositorLayoutChanged() {
            applyCompositorConfig();
        }
        function onCompositorLayoutReadyChanged() {
            if (GlobalStates.compositorLayoutReady) {
                applyCompositorConfig();
            }
        }
    }

    // Re-apply once the axctl daemon is ready, so the initial animations fetch
    // succeeds instead of racing the daemon socket at startup.
    property Connections axctlReadyConnections: Connections {
        target: AxctlService
        function onReadyChanged() {
            if (AxctlService.ready)
                applyCompositorConfig();
        }
    }


    Component.onCompleted: {
        // Apply immediately if Config is already loaded.
        if (Config.loader.loaded) {
            applyCompositorConfig();
        }
        // Otherwise, handled by onLoaded.
    }
}
