# Visual & Data Quality Reference

Based on the Financial Times Visual Vocabulary, Edward Tufte's principles, and common data visualization failures.

## FT Visual Vocabulary: Chart Selection

Match chart type to the relationship you're showing. Using the wrong chart type is the most common data visualization mistake.

| Relationship | Best Chart Types | Common Mistakes |
|---|---|---|
| **Deviation** (variation from baseline) | Diverging bar, diverging stacked bar, surplus/deficit line | Using standard bar when data has +/- values |
| **Correlation** (relationship between variables) | Scatterplot, connected scatterplot, bubble | Dual-axis charts implying spurious correlation |
| **Ranking** (position in ordered list) | Ordered bar, slope chart, lollipop | Unsorted bars that obscure rank |
| **Distribution** (values and frequency) | Histogram, boxplot, violin plot | Too few bins hiding distribution shape |
| **Change over time** (temporal trends) | Line, column, area, fan chart | Area charts where component changes are invisible |
| **Part-to-whole** (component breakdown) | Stacked bar, treemap, waterfall | Pie charts with too many segments (>5) |
| **Magnitude** (comparing sizes) | Bar/column, proportional symbol, lollipop | 3D bars obscuring values behind other bars |
| **Spatial** (geographic data) | Choropleth, proportional symbol, dot density | Choropleth for absolute counts (should use rates) |
| **Flow** (movement/transformation) | Sankey, waterfall, chord diagram | Overloaded Sankey with too many paths to read |

## Tufte's Core Principles

### Data-Ink Ratio
Maximize the proportion of ink showing actual data vs. total ink on the graphic. Every non-data element (gridlines, borders, decoration) must justify its existence.

### Graphical Integrity
Visual representation must be proportional to the data. A bar twice as tall must represent a value twice as large.

### Chart Junk
Unnecessary decorative elements that detract from data communication: 3D effects, gradient fills, decorative icons, unnecessary gridlines. If it doesn't help the reader understand the data, remove it.

### Clear Labeling
Label data directly rather than using legends that force the reader to look back and forth. Annotations on the chart explaining important patterns are better than making readers interpret raw data.

### Show the Data
"Above all else, show the data." Design serves data, not the reverse.

## Data Quality Issues to Flag

### Misleading Practices

| Issue | What to Look For | Why It Matters |
|---|---|---|
| **Truncated Y-axis** | Bar charts not starting at zero | Makes small differences look dramatic |
| **Cherry-picked timeframe** | Date range that shows only favorable trend | Hides the full picture |
| **Dual Y-axes** | Two scales implying correlation | Readers assume the lines are comparable |
| **Area/volume distortion** | Pictograms sized by radius not area | 3x difference looks like 9x |
| **Inconsistent intervals** | Uneven time spacing plotted as even | Distorts rate of change |
| **Unlabeled axes** | Missing units, scale, or labels | Reader can't verify or interpret the data |
| **Missing source** | No citation for the underlying data | Unverifiable claims dressed as data |
| **Survivorship bias** | Only showing successes | Misleading conclusions about what works |

### Chart Quality Checklist

Apply to every chart, graph, or data visualization in the piece:

- [ ] **Right chart type?** Does it match the data relationship (see FT table above)?
- [ ] **Labeled axes?** Units, scale, and axis titles present?
- [ ] **Source cited?** Where does this data come from? Date of data?
- [ ] **Honest scales?** Y-axis starts at zero for bar charts? No misleading truncation?
- [ ] **Readable?** Can you understand the chart in 10 seconds without the caption?
- [ ] **No chart junk?** No unnecessary 3D, gradients, decoration?
- [ ] **Direct labels?** Data labeled on-chart rather than via a distant legend?
- [ ] **Color accessible?** Works in grayscale? Distinguishable for color-blind readers?
- [ ] **Appropriate precision?** Not implying more accuracy than the data supports?
- [ ] **Context provided?** Comparisons, benchmarks, or baselines for interpretation?

### Data Analysis Quality

Beyond chart execution, evaluate the analytical thinking:

| Issue | Flag When |
|---|---|
| **Correlation ≠ causation** | Two trends shown together with implied causal link |
| **Small sample size** | Conclusions drawn from handful of data points |
| **Selection bias** | Sample doesn't represent the population discussed |
| **Percentage of unknown base** | "Up 50%" without stating the starting number |
| **Averages hiding distribution** | Mean reported when median or distribution matters |
| **Extrapolation beyond data** | Trend line extended far past available data |
| **Missing denominator** | Raw counts compared across different-sized groups |
| **Confounding variables** | Obvious alternative explanations not addressed |
