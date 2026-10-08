---
title: Tide Station Notes
tags: [harbour, tides]
aliases:
  - tide notes
created: 2024-05-02
---

# Tide Station Notes

Readings are copied from [[Tide Log 2024]] and the [[Station Map|map of the stations]].

![[station-photo.png]]

> [!warning] Calibration due
> The north gauge drifts by 2 cm a month. See [[Calibration#Procedure]].

> [!note]- Folded note
> Folded callouts start collapsed in Obsidian.

## Tasks

- [x] Replace the gauge battery
- [ ] Re-level the staff board
    - [ ] Borrow the dumpy level

## Readings

| Station | High (m) | Low (m) |
|:--|--:|--:|
| North | 4.2 | 0.6 |
| South | 3.9 | 0.8 |

The south gauge sits in a sheltered inlet.[^shelter]

```python
def range_m(high, low):
    return round(high - low, 2)
```

<details>
<summary>Raw export</summary>

north,4.2,0.6

</details>

Tagged #tides and #harbour/maintenance.

[^shelter]: The inlet halves the wave height compared with the open shore.
