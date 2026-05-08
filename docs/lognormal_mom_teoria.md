# Rozkład Log-Normalny dopasowany Metodą Momentów: teoria i przedziały ufności

## 1. Sformułowanie problemu

Analiza częstości wezbrań polega na wyznaczeniu przepływu $Q_T$, który statystycznie jest przekraczany średnio raz na $T$ lat — tzw. **przepływu o okresie powrotu $T$**. Wyznaczane tu wartości projektowe to $Q_{100}$ (prawdopodobieństwo przewyższenia 1% w roku) oraz $Q_{1000}$ (prawdopodobieństwo 0,1%).

Podstawą analizy jest seria **rocznych maksymalnych przepływów** $\{Q_1, Q_2, \ldots, Q_n\}$, gdzie $Q_i$ oznacza największy dobowy przepływ średni zarejestrowany na stacji w hydrologicznym roku $i$.

---

## 2. Rozkład Log-Normalny

Dwuparametrowy model **log-normalny** zakłada, że logarytm naturalny przepływu ma rozkład normalny:

$$\ln Q \sim \mathcal{N}(\mu,\, \sigma^2)$$

Gęstość prawdopodobieństwa zmiennej $Q$ wynosi:

$$f_Q(q) = \frac{1}{q\,\sigma\sqrt{2\pi}} \exp\!\left(-\frac{(\ln q - \mu)^2}{2\sigma^2}\right), \quad q > 0$$

Dystrybuantę (CDF) można zapisać poprzez dystrybuantę standardowego rozkładu normalnego $\Phi$:

$$F_Q(q) = \Phi\!\left(\frac{\ln q - \mu}{\sigma}\right)$$

Parametry $\mu$ i $\sigma$ są odpowiednio średnią i odchyleniem standardowym zmiennej $\ln Q$, nie zaś samego przepływu $Q$.

---

## 3. Estymacja parametrów — Metoda Momentów

**Metoda Momentów** (MM) polega na przyrównaniu teoretycznych momentów rozkładu do odpowiadających im momentów próbkowych. W przypadku rozkładu log-normalnego jest to szczególnie wygodne, ponieważ momentami zmiennej $\ln Q$ są bezpośrednio jej parametry.

Dla próby $\{Q_1, \ldots, Q_n\}$ złożonej z $n$ wartości dodatnich estymatory MM mają postać:

$$\hat{\mu} = \frac{1}{n}\sum_{i=1}^{n} \ln Q_i$$

$$\hat{\sigma} = \sqrt{\frac{1}{n-1}\sum_{i=1}^{n}\left(\ln Q_i - \hat{\mu}\right)^2}$$

Odchylenie standardowe próbki liczone jest z korektą Bessela (mianownik $n-1$), co zapewnia nieobciążoność estymatora wariancji populacji.

---

## 4. Estymacja kwantyli

**Przepływ o okresie powrotu $T$** odpowiada prawdopodobieństwu przewyższenia $p = 1/T$. Kwantyl teoretyczny otrzymuje się przez odwrócenie dystrybuanty:

$$Q_T = F_Q^{-1}\!\left(1 - \frac{1}{T}\right)$$

Podstawiając dystrybuantę rozkładu log-normalnego i korzystając z odwrotności dystrybuanty normalnej $\Phi^{-1}$:

$$\boxed{Q_T = \exp\!\left(\hat{\mu} + \hat{\sigma}\cdot\Phi^{-1}\!\left(1 - \frac{1}{T}\right)\right)}$$

Oznaczając $z_p = \Phi^{-1}(p)$ jako kwantyl standardowego rozkładu normalnego przy prawdopodobieństwie skumulowanym $p$ oraz pamiętając, że prawdopodobieństwo przewyższenia wynosi $p = 1/T$:

$$Q_T = \exp\!\left(\hat{\mu} - \hat{\sigma}\cdot z_{1/T}\right)$$

Wartości dla dwóch rozpatrywanych okresów powrotu:

| Okres powrotu $T$ | Prawdopodobieństwo przewyższenia $p$ | Kwantyl normalny $z_{1-p}$ |
|:-----------------:|:------------------------------------:|:--------------------------:|
| 100 lat           | 1,0 %                                | 2,326                      |
| 1000 lat          | 0,1 %                                | 3,090                      |

---

## 5. Empiryczne prawdopodobieństwa empiryczne

Aby zwizualizować dopasowanie, obserwowanym rocznym maksimom przypisuje się empiryczne prawdopodobieństwa przewyższenia według wzoru **Hazena (metoda rang średnich)**:

$$\hat{p}_m = \frac{n - m + 0{,}5}{n}$$

gdzie $m = 1, 2, \ldots, n$ jest rangą obserwacji posortowanych rosnąco ($m = 1$ to wartość najmniejsza, o największej częstości przewyższenia). Formuła Hazena umieszcza każdą obserwację w środku jej przedziału prawdopodobieństwa, co jest nieobciążone dla mediany statystyk pozycyjnych przy rozkładzie jednostajnym.

Krzywa teoretyczna $Q(p)$ oraz punkty empiryczne są nanoszone na oś $x$ w skali kwantyla normalnego $z = \Phi^{-1}(p)$, tworząc **wykres prawdopodobieństwa log-normalnego**. Na tej skali rozkład log-normalny odpowiada prostej linii, co pozwala graficznie ocenić zgodność danych z modelem.

---

## 6. Przedziały ufności — bootstrap

Estymaty punktowe $\hat{Q}_{100}$ i $\hat{Q}_{1000}$ obarczone są niepewnością wynikającą z ograniczonej liczebności próby, na podstawie której wyznaczono $\hat{\mu}$ i $\hat{\sigma}$. Do kwantyfikacji tej niepewności dla całej krzywej kwantylowej $Q(p)$ zastosowano **bootstrap percentylowy**.

### 6.1 Procedura

Niech obserwowana seria wynosi $\mathbf{Q} = (Q_1, \ldots, Q_n)$, gdzie wszystkie $n$ wartości są dodatnie. Procedurę powtarza się $B = 5\,000$ razy:

1. Losuje się próbę bootstrapową $\mathbf{Q}^{(b)} = (Q_1^{(b)}, \ldots, Q_n^{(b)})$ o liczebności $n$ **ze zwracaniem** z $\mathbf{Q}$.
2. Dopasowuje się estymator log-normalny MM do $\mathbf{Q}^{(b)}$, uzyskując $\hat{\mu}^{(b)}$ i $\hat{\sigma}^{(b)}$.
3. Oblicza się krzywą kwantylową na gęstej siatce prawdopodobieństw $p_1, \ldots, p_K$:

$$Q^{(b)}(p_k) = \exp\!\left(\hat{\mu}^{(b)} + \hat{\sigma}^{(b)}\cdot\Phi^{-1}(1 - p_k)\right)$$

W wyniku otrzymuje się macierz $B \times K$ bootstrapowych krzywych kwantylowych.

### 6.2 Pasma ufności

Dla każdego prawdopodobieństwa $p_k$ sortuje się $B$ wartości bootstrapowych $Q^{(1)}(p_k), \ldots, Q^{(B)}(p_k)$ i wyznacza empiryczne kwantyle:

$$\hat{Q}^{\,\text{dół}}(p_k) = \text{kwantyl}\!\left(\left\{Q^{(b)}(p_k)\right\}_{b=1}^{B},\; \frac{\alpha}{2}\right)$$

$$\hat{Q}^{\,\text{góra}}(p_k) = \text{kwantyl}\!\left(\left\{Q^{(b)}(p_k)\right\}_{b=1}^{B},\; 1 - \frac{\alpha}{2}\right)$$

Dla $\alpha = 0{,}10$ otrzymane pasmo stanowi **90-procentowy przedział ufności** krzywej kwantylowej: $[\hat{Q}^{\,\text{dół}}(p),\; \hat{Q}^{\,\text{góra}}(p)]$.

Metoda bootstrapu percentylowego nie zakłada żadnego konkretnego rozkładu estymatora i odzwierciedla pełną zmienność próbkową wynikającą jednocześnie z losowości $\hat{\mu}$ i $\hat{\sigma}$.

### 6.3 Interpretacja

Pasmo ufności odpowiada na pytanie: *jeśli prawdziwy rozkład jest log-normalny, a próba liczy $n$ obserwacji, jak bardzo zmieniałaby się dopasowana krzywa kwantylowa przy hipotetycznym wielokrotnym losowaniu próby?* Szerokie pasmo dla dużych okresów powrotu (małe $p$) odzwierciedla trudność estymacji ekstremalnych kwantyli na podstawie krótkich serii obserwacyjnych.

---

## 7. Zestawienie oznaczeń

| Symbol | Znaczenie |
|--------|-----------|
| $Q_i$ | Roczny maksymalny przepływ w roku $i$ [m³/s] |
| $n$ | Liczba lat obserwacji |
| $\mu$ | Średnia $\ln Q$ (parametr położenia rozkładu log-normalnego) |
| $\sigma$ | Odchylenie standardowe $\ln Q$ (parametr skali) |
| $T$ | Okres powrotu [lata] |
| $p = 1/T$ | Roczne prawdopodobieństwo przewyższenia |
| $\Phi^{-1}$ | Odwrotna dystrybuanta standardowego rozkładu normalnego (funkcja probit) |
| $z_p = \Phi^{-1}(p)$ | Kwantyl normalny przy prawdopodobieństwie skumulowanym $p$ |
| $Q_T$ | Przepływ projektowy dla okresu powrotu $T$ [m³/s] |
| $B$ | Liczba prób bootstrapowych (5 000) |
| $\alpha$ | Poziom istotności przedziału ufności (0,10) |
