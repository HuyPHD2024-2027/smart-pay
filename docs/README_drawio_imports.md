# Draw.io (diagrams.net) Import Guide
## MeshPay Flow Diagrams

This directory contains mxGraphModel XML files that can be imported into draw.io (diagrams.net) for visualization and editing.

---

## Files Created

1. **`transfer_order_flow_drawio.xml`** - Transfer Order Flow diagram
2. **`withdrawal_protocol_flow_drawio.xml`** - Withdrawal Protocol Flow diagram  
3. **`mxGraphModel_flows.xml`** - Combined file with both diagrams (recommended)

---

## How to Import into Draw.io

### Method 1: Import Combined File (Recommended)

1. Open [draw.io](https://app.diagrams.net) in your browser
2. Click **File** → **Open from** → **Device**
3. Select `mxGraphModel_flows.xml`
4. Both diagrams will be imported as separate pages/tabs
5. You can switch between them using the tabs at the bottom

### Method 2: Import Individual Files

1. Open [draw.io](https://app.diagrams.net)
2. Click **File** → **Open from** → **Device**
3. Select either:
   - `transfer_order_flow_drawio.xml` for Transfer Order Flow
   - `withdrawal_protocol_flow_drawio.xml` for Withdrawal Protocol Flow

---

## Diagram Details

### Transfer Order Flow

**Swimlanes:**
- **Client** (Blue) - Client-side operations
- **Mesh Network** (Orange) - Mesh routing operations
- **Authorities** (Green) - Authority validation and signing

**Steps:**
1. Create TransferOrder
2. Sign TransferOrder
3. Broadcast
4. Route (multi-hop)
5. Validate
6. Sign
7. Certificate
8. Collect Signatures
9. Check Quorum (≥2/3)
10. Create Confirmation
11. Broadcast
12. Forward
13. Update State
14. Finalized

### Withdrawal Protocol Flow

**Swimlanes:**
- **Client** (Blue) - Client-side operations
- **Authorities** (Green) - Authority validation and signing
- **Gateway** (Orange) - Gateway processing
- **Primary Ledger** (Purple) - Blockchain/RTGS operations

**Steps:**
1. Create Withdrawal Order
2. Sign Order
3. Broadcast
4. Validate (balance, sequence, partition)
5. Lock Balance
6. Sign Order
7. Certificate
8. Collect Quorum (≥2/3)
9. Create Certificate
10. Submit
11. Validate Certificate
12. Submit Settlement
13. Execute Settlement
14. Confirm
15. Update Mesh State
16. Broadcast State Update
17. Debit Balance
18. Finalized

---

## Editing the Diagrams

After importing, you can:

1. **Modify Colors:** Right-click on shapes → **Format** → **Fill**
2. **Add Labels:** Double-click on arrows to add labels
3. **Resize:** Click and drag corners of shapes
4. **Reposition:** Click and drag shapes
5. **Add Notes:** Insert text boxes for additional information
6. **Export:** File → Export as → PNG, SVG, PDF, etc.

---

## Color Scheme

| Component | Color | Hex Code |
|-----------|-------|----------|
| Client | Light Blue | #E1F5FF / #BBDEFB |
| Mesh Network | Light Orange | #FFF4E1 / #FFE0B2 |
| Authorities | Light Green | #E8F5E9 / #C8E6C9 |
| Gateway | Light Orange | #FFF4E1 / #FFE0B2 |
| Primary Ledger | Light Purple | #F3E5F5 / #E1BEE7 |
| Finalized | Success Green | #C8E6C9 |

---

## Export Options

After editing, you can export the diagrams as:

- **PNG** - For presentations and documents
- **SVG** - For scalable vector graphics
- **PDF** - For documentation
- **XML** - For saving edits back to XML format

---

## Troubleshooting

### Diagram doesn't appear after import
- Make sure you're importing the `.xml` file, not opening it directly
- Try refreshing the page and importing again

### Shapes are overlapping
- Use **Arrange** → **Layout** → **Auto Layout** to reorganize
- Manually drag shapes to reposition

### Arrows are misaligned
- Select the arrow and use **Format** → **Line** → **Style** to adjust
- Use **Arrange** → **Align** to align shapes properly

---

## File Structure

The mxGraphModel format uses:
- **`<mxGraphModel>`** - Root element with page settings
- **`<root>`** - Container for all diagram elements
- **`<mxCell>`** - Individual shapes and connections
  - **`vertex="1"`** - For shapes/boxes
  - **`edge="1"`** - For arrows/connections
- **`style`** - Defines appearance (colors, fonts, etc.)
- **`geometry`** - Defines position and size

---

## Notes

- The diagrams are designed for A4/Letter page size
- All coordinates are in pixels
- Colors follow Material Design color palette
- Font sizes are optimized for readability
- Arrows use orthogonal edge style for clean appearance

---

**Last Updated:** January 2025  
**Format:** mxGraphModel (draw.io compatible)
