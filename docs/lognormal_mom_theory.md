# Log-Normal Distribution Fitted by the Method of Moments: Theory and Confidence Intervals

## 1. Problem Statement

Flood frequency analysis aims to estimate the discharge $Q_T$ that is exceeded on average once every $T$ years — the **$T$-year flood**. The two design events considered here are $Q_{100}$ (1% annual exceedance probability) and $Q_{1000}$ (0.1% annual exceedance probability).

The analysis is based on a series of **annual maximum flows** $\{Q_1, Q_2, \ldots, Q_n\}$, where each $Q_i$ is the largest daily mean discharge recorded at the station during hydrological year $i$.

---

## 2. The Log-Normal Distribution

The two-parameter **Log-Normal** model assumes that the natural logarithm of discharge follows a normal distribution:

$$\ln Q \sim \mathcal{N}(\mu,\, \sigma^2)$$

The probability density function of $Q$ is:

$$f_Q(q) = \frac{1}{q\,\sigma\sqrt{2\pi}} \exp\!\left(-\frac{(\ln q - \mu)^2}{2\sigma^2}\right), \quad q > 0$$

The cumulative distribution function (CDF) can be written in terms of the standard normal CDF $\Phi$:

$$F_Q(q) = \Phi\!\left(\frac{\ln q - \mu}{\sigma}\right)$$

The parameters $\mu$ and $\sigma$ are the mean and standard deviation of the log-transformed variable, not of $Q$ itself.

---

## 3. Parameter Estimation — Method of Moments

The **Method of Moments** (MoM) equates the theoretical moments of the distribution to the corresponding sample moments. For the Log-Normal distribution, this is particularly convenient because the moments of $\ln Q$ are the parameters themselves.

Given a sample $\{Q_1, \ldots, Q_n\}$ of $n$ positive observations, the MoM estimators are:

$$\hat{\mu} = \frac{1}{n}\sum_{i=1}^{n} \ln Q_i$$

$$\hat{\sigma} = \sqrt{\frac{1}{n-1}\sum_{i=1}^{n}\left(\ln Q_i - \hat{\mu}\right)^2}$$

The sample standard deviation uses Bessel's correction (denominator $n-1$) to obtain an unbiased estimate of the population variance.

---

## 4. Quantile Estimation

The **$T$-year discharge** corresponds to the exceedance probability $p = 1/T$. The theoretical quantile is obtained by inverting the CDF:

$$Q_T = F_Q^{-1}\!\left(1 - \frac{1}{T}\right)$$

Substituting the Log-Normal CDF and using the inverse standard normal $\Phi^{-1}$:

$$\boxed{Q_T = \exp\!\left(\hat{\mu} + \hat{\sigma}\cdot\Phi^{-1}\!\left(1 - \frac{1}{T}\right)\right)}$$

Equivalently, denoting $z_p = \Phi^{-1}(p)$ as the standard normal quantile at cumulative probability $p$, and noting that the exceedance probability is $p = 1/T$:

$$Q_T = \exp\!\left(\hat{\mu} - \hat{\sigma}\cdot z_{1/T}\right)$$

For the two design return periods:

| Return period $T$ | Exceedance probability $p$ | Standard normal quantile $z_{1-p}$ |
|:-----------------:|:--------------------------:|:-----------------------------------:|
| 100 years         | 1.0 %                      | 2.326                               |
| 1000 years        | 0.1 %                      | 3.090                               |

---

## 5. Empirical Plotting Positions

To visualise the fit, observed annual maxima are assigned empirical exceedance probabilities using the **Hazen (mean-rank)** formula:

$$\hat{p}_m = \frac{n - m + 0.5}{n}$$

where $m = 1, 2, \ldots, n$ is the rank of the observation sorted in **ascending** order ($m = 1$ is the smallest value, highest exceedance frequency). Hazen positions place each observation at the midpoint of its probability interval, which is unbiased for the median of the order statistics under a uniform distribution.

The theoretical curve $Q(p)$ and empirical points are both plotted against the standard normal quantile $z = \Phi^{-1}(p)$ on the $x$-axis, producing the **Log-Normal probability plot**. On this scale, a Log-Normal distribution plots as a straight line, making departures from the model visually apparent.

---

## 6. Confidence Interval — Parametric Bootstrap

The point estimates $\hat{Q}_{100}$ and $\hat{Q}_{1000}$ carry sampling uncertainty because $\hat{\mu}$ and $\hat{\sigma}$ are estimated from a finite sample. A **parametric bootstrap** is used to quantify this uncertainty across the entire quantile curve $Q(p)$.

### 6.1 Procedure

Let the observed series be $\mathbf{Q} = (Q_1, \ldots, Q_n)$ with $n$ positive values. Repeat $B = 5{,}000$ times:

1. Draw a resample $\mathbf{Q}^{(b)} = (Q_1^{(b)}, \ldots, Q_n^{(b)})$ of size $n$ **with replacement** from $\mathbf{Q}$.
2. Fit the Log-Normal MoM estimator to $\mathbf{Q}^{(b)}$, obtaining $\hat{\mu}^{(b)}$ and $\hat{\sigma}^{(b)}$.
3. Evaluate the quantile curve at a dense probability grid $p_1, \ldots, p_K$:

$$Q^{(b)}(p_k) = \exp\!\left(\hat{\mu}^{(b)} + \hat{\sigma}^{(b)}\cdot\Phi^{-1}(1 - p_k)\right)$$

This yields a $B \times K$ matrix of bootstrap quantile curves.

### 6.2 Confidence Bands

For each probability $p_k$, sort the $B$ bootstrap values $Q^{(1)}(p_k), \ldots, Q^{(B)}(p_k)$ and take the empirical quantiles:

$$\hat{Q}^{\,\text{lo}}(p_k) = \text{quantile}\!\left(\left\{Q^{(b)}(p_k)\right\}_{b=1}^{B},\; \frac{\alpha}{2}\right)$$

$$\hat{Q}^{\,\text{hi}}(p_k) = \text{quantile}\!\left(\left\{Q^{(b)}(p_k)\right\}_{b=1}^{B},\; 1 - \frac{\alpha}{2}\right)$$

With $\alpha = 0.10$, the resulting band is a **90% confidence interval** on the theoretical quantile curve: $[\hat{Q}^{\,\text{lo}}(p), \hat{Q}^{\,\text{hi}}(p)]$.

This approach — the **percentile bootstrap** — does not assume any particular distribution for the estimator and captures the full sampling variability induced by both $\hat{\mu}$ and $\hat{\sigma}$ simultaneously.

### 6.3 Interpretation

The confidence band answers the question: *given that the true distribution is Log-Normal and the sample is of size $n$, how much would the fitted quantile curve vary across hypothetical repeated samples?* A wide band at high return periods (low $p$) reflects the inherent difficulty of estimating extreme quantiles from short records.

---

## 7. Summary of Notation

| Symbol | Meaning |
|--------|---------|
| $Q_i$ | Annual maximum flow in year $i$ [m³/s] |
| $n$ | Number of years of record |
| $\mu$ | Mean of $\ln Q$ (Log-Normal location parameter) |
| $\sigma$ | Standard deviation of $\ln Q$ (Log-Normal scale parameter) |
| $T$ | Return period [years] |
| $p = 1/T$ | Annual exceedance probability |
| $\Phi^{-1}$ | Inverse standard normal CDF (probit function) |
| $z_p = \Phi^{-1}(p)$ | Standard normal quantile at cumulative probability $p$ |
| $Q_T$ | Design discharge for return period $T$ [m³/s] |
| $B$ | Number of bootstrap resamples (5 000) |
| $\alpha$ | Significance level for confidence interval (0.10) |
