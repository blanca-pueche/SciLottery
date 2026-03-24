# 🎲 SciLottery

**A computational tool for research funding under uncertainty**

---

## Overview

SciLottery implements the models described in *“Research Funding as a Decision Problem Under Heavy-Tailed Uncertainty.”* It provides a practical framework to compute and explore funding allocations based on bibliometric data and decision-theoretic principles.

The tool is designed to study how different allocation strategies behave when scientific impact is inherently uncertain and unevenly distributed.

---

## Conceptual Framework

SciLottery is based on three key assumptions:

- Scientific impact follows a **heavy-tailed distribution** and is only partially predictable  
- Past performance provides **statistically meaningful but imperfect signals** of future outcomes  
- Allocation rules optimized purely for expected impact tend to produce **highly concentrated funding**

To address these issues, SciLottery implements **deterministic allocation rules** that explicitly balance:

- **Exploitation** of predictive signals  
- **Exploration** under uncertainty  

---

## Functionality

Given a set of researchers and their performance indicators, SciLottery:

- Computes **normalized performance scores** (e.g., percentile-based aggregates)  
- Transforms these scores into **allocation rules or selection probabilities**  
- Enables comparison between:
  - **Concentrated** allocations  
  - **Uniform** allocations  
  - **Lottery-based** allocations

---

## Purpose

SciLottery is not a decision system, but a **calculator** to:

- Evaluate how different funding policies behave under realistic assumptions  
- Quantify the effects of concentration, exploration, and randomness  
- Support the analysis of funding strategies in the presence of uncertainty  

---

## Use Cases

- Research policy analysis  
- Simulation of funding allocation strategies  
- Exploration of trade-offs between fairness and efficiency  
- Study of uncertainty in scientific evaluation systems  

---

## Notes

This tool is intended for **analysis and experimentation**, not for direct decision-making. Its goal is to make the consequences of different allocation rules explicit and measurable.

---