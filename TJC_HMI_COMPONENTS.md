# TJC8048X350_01R HMI component setup

Project resolution: **800 x 480**, landscape.

Create one page named `page0`. Add `bg_tjc_800x480.png` to the Picture library
and use it as the page background.

## Live reading text components

Set alignment to horizontal centre and vertical centre. Disable touch for all
three components.

| Name | x | y | w | h | Font | Text colour | Background |
|---|---:|---:|---:|---:|---|---|---|
| `tOxygen` | 20 | 155 | 235 | 168 | Arial Bold, about 96 px | Black (`0`) | White (`65535`) |
| `tAir` | 282 | 155 | 235 | 168 | Arial Bold, about 96 px | Black (`0`) | White (`65535`) |
| `tVacuum` | 545 | 155 | 235 | 168 | Arial Bold, about 82 px | Black (`0`) | White (`65535`) |

Initial text for each reading should be `--`.

Recommended attributes:

- `sta=1` (solid colour)
- `bco=65535`
- `pco=0`
- `xcen=1`
- `ycen=1`

## Status text components

| Name | x | y | w | h | Font | Initial text |
|---|---:|---:|---:|---:|---|
| `tOxygenStatus` | 20 | 376 | 235 | 67 | Arial Bold, about 25 px | `WAITING` |
| `tAirStatus` | 282 | 376 | 235 | 67 | Arial Bold, about 25 px | `WAITING` |
| `tVacuumStatus` | 545 | 376 | 235 | 67 | Arial Bold, about 25 px | `WAITING` |

Recommended attributes:

- `sta=1`
- `bco=50712` (light green; choose the nearest available colour if needed)
- `pco=2016` (green)
- `xcen=1`
- `ycen=1`

## Alarm variables

Add three Variable components. Set their type to Number, initial value to `0`,
and variable scope (`vscope`) to Global.

| Name | Initial value |
|---|---:|
| `vaOxygenAlarm` | 0 |
| `vaAirAlarm` | 0 |
| `vaVacuumAlarm` | 0 |

These names are required because the Pico sends commands such as:

```text
vaOxygenAlarm.val=1
vaAirAlarm.val=0
vaVacuumAlarm.val=1
```

## Alarm blink timer

Add a Timer component:

- Name: `tmBlink`
- `tim=500`
- `en=1`

Put this code in the timer event:

```text
if(vaOxygenAlarm.val==1)
{
  if(tOxygen.pco==51200)
  {
    tOxygen.pco=0
    vis tOxygen,0
    vis tOxygenStatus,0
  }else
  {
    tOxygen.pco=51200
    tOxygenStatus.pco=51200
    tOxygenStatus.bco=64560
    vis tOxygen,1
    vis tOxygenStatus,1
  }
}else
{
  vis tOxygen,1
  vis tOxygenStatus,1
  tOxygen.pco=0
  tOxygenStatus.pco=736
  tOxygenStatus.bco=51192
}

if(vaAirAlarm.val==1)
{
  if(tAir.pco==51200)
  {
    tAir.pco=0
    vis tAir,0
    vis tAirStatus,0
  }else
  {
    tAir.pco=51200
    tAirStatus.pco=51200
    tAirStatus.bco=64560
    vis tAir,1
    vis tAirStatus,1
  }
}else
{
  vis tAir,1
  vis tAirStatus,1
  tAir.pco=0
  tAirStatus.pco=736
  tAirStatus.bco=51192
}

if(vaVacuumAlarm.val==1)
{
  if(tVacuum.pco==51200)
  {
    tVacuum.pco=0
    vis tVacuum,0
    vis tVacuumStatus,0
  }else
  {
    tVacuum.pco=51200
    tVacuumStatus.pco=51200
    tVacuumStatus.bco=64560
    vis tVacuum,1
    vis tVacuumStatus,1
  }
}else
{
  vis tVacuum,1
  vis tVacuumStatus,1
  tVacuum.pco=0
  tVacuumStatus.pco=736
  tVacuumStatus.bco=51192
}
```

Alarm colours are `bco=64560`, `pco=51200`. Normal colours are
`bco=51192`, `pco=736`.

## Picture assets

Import these theme-matched files from the `tjc_assets_theme` directory into
the TJC Picture library:

```text
mute_action.png
unmute_action.png
ethernet_connected_icon.png
ethernet_disconnected_icon.png
test_ready.png
test_active.png
```

## Mute picture button

Add a **Dual-state Button**:

- Name: `bMute`
- Position: `x=18`, `y=39`, `w=150`, `h=60`
- Initial value: `0`
- State 0 picture: `mute_action.png` (the action available is MUTE)
- State 1 picture: `unmute_action.png` (the action available is UNMUTE)
- Do not add text; it is already inside the pictures.

Place this code in its **Touch Release Event**:

```text
if(bMute.val==1)
{
  prints "MUTE_ON",0
  printh 0A
}else
{
  prints "MUTE_OFF",0
  printh 0A
}
```

The Pico synchronizes the button with `bMute.val=0` or `bMute.val=1`.

## Test button

Add a **Dual-state Button**:

- Name: `bTest`
- Position: `x=640`, `y=39`, `w=150`, `h=60`
- Initial value: `0`
- State 0 picture: `test_ready.png`
- State 1 picture: `test_active.png`
- Do not add text; it is already inside the pictures.

Place this code in its **Touch Release Event**:

```text
prints "TEST_START",0
printh 0A
```

## Ethernet status indicator

Add a Picture component:

- Name: `pEthernetOff`
- Position: `x=174`, `y=39`, `w=52`, `h=60`
- Picture: `ethernet_disconnected_icon.png`
- Initial visibility: visible

Add a Picture component directly on top of it:

- Name: `pWifi` (kept for firmware compatibility)
- Position: `x=174`, `y=39`, `w=52`, `h=60`
- Picture: `ethernet_connected_icon.png`
- Initial visibility: hidden

Although the component is called `pWifi`, it represents the W5500/dashboard
connection. The Pico controls it with `vis pWifi,1` and `vis pWifi,0`.

Put this code in `page0`'s **PostInitialize Event** so both indicators start
hidden until the Pico supplies their real state:

```text
vis pWifi,0
```

## Required component-name checklist

```text
tOxygen
tAir
tVacuum
tOxygenStatus
tAirStatus
tVacuumStatus
vaOxygenAlarm
vaAirAlarm
vaVacuumAlarm
tmBlink
bMute
bTest
pEthernetOff
pWifi
```

Names are case-sensitive and must match exactly.
