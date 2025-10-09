---
title: Evolución y ventas de los CEO de Porsche Ibérica
description: Descubre la historia de Porsche en España a través de sus CEO. Analizamos 40 años de evolución, ventas y liderazgo, desde su fundación hasta la actual era eléctrica.
image: 
author: Emirodgar
lang: es_ES
sitemap: 1
feed: 1
date: 05/10/2025
folder: Análisis
permalink: ceos-porsche
---

# Evolución, rendimiento y ventas de los CEO de Porsche en España

La historia de Porsche en España ha estado marcada por el liderazgo de diversos directores generales que han guiado la marca a través de diferentes etapas de crecimiento y transformación. Desde la fundación de Porsche España en 1984 hasta la actualidad como Porsche Ibérica, cada CEO ha dejado su huella particular en el desarrollo de la marca en el mercado ibérico.

## **Los Pioneros: estableciendo los cimientos (1984-1997)**

### **Ulrich Friedrich Oskar Heyl (1984-1997) - El fundador**

**Ulrich Friedrich Oskar Heyl fue el primer Director General de Porsche España**, proveniente del área de Formación de Porsche AG en Alemania. Su llegada marcó el inicio de una nueva era cuando el 17 de mayo de 1984, Porsche AG y Porsche Holding adquirieron las acciones de Turbomotor, el anterior importador privado de la marca.

**Logros y desafíos iniciales:**

- En **1985, primer año completo de operaciones, Porsche España vendió 252 unidades**
- Más de la mitad (57%) eran modelos transaxle de cuatro cilindros: el 924 y el 944
- Se vendieron **12 unidades del mítico Porsche 959**
- La plantilla creció de 15 a 32 personas durante el primer año
- Establecimiento de una red inicial de 10 concesionarios

Heyl enfrentó enormes desafíos económicos, incluyendo un **impuesto de lujo del 33% más aranceles**, y la fortaleza del marco alemán que había aumentado casi un 50% entre 1980 y 1984. Un Porsche 911 Carrera 3.2 costaba aproximadamente 40.000 euros en 1984, equivalentes a 162.000 euros actuales.[^1_1][^1_5]

## **La Era de expansión y modernización (1997-2010)**

### **Peter Schwarzenbauer (1997-2003) - El visionario**

**Peter Schwarzenbauer asumió la Dirección General de Porsche Ibérica en 1997**, coincidiendo con un cambio fundamental en la estructura de la compañía. Nacido en 1959 en Weissenburg (Alemania), llegó a Porsche como Director Comercial para Alemania en 1994 antes de trasladarse a España.

**Transformaciones clave:**

- **Cambio de control corporativo**: En 1997, Porsche AG tomó el control total de la filial, que pasó de llamarse Porsche España a Porsche Ibérica
- Cambio en las exigencias: De presión financiera (bajo Porsche Holding) a presión de ventas (bajo Porsche AG)
- **Periodo de florecimiento con nuevos modelos** durante su mandato
- Implementación gradual de las directrices alemanas en la filial española

Los años de Schwarzenbauer fueron de **continua expansión** y cuando se marchó en 2003, la empresa vivía "un momento dulce". Su liderazgo coincidió con la llegada de modelos revolucionarios que transformarían la percepción de Porsche.

### **Joachim Lamla (2003-2010) - El consolidador**

**Joachim Lamla fue Director General de Porsche Ibérica de 2003 a 2009**, llegando a la compañía tras haber ingresado en Porsche AG en 1995. Durante sus siete años al frente, la empresa **"afrontó con éxito varios retos"**.

**Principales logros:**

- **Desvinculación exitosa de la marca Saab** del negocio de Porsche en España
- **Profunda renovación de la gama de productos**
- **Expansión significativa de la red de concesionarios oficiales**
- Gestión durante el periodo de lanzamiento del **Cayenne**, que revolucionaría las ventas de Porsche

Lamla demostró una **notable capacidad de gestión durante crisis**, navegando los desafíos del final de los años 2000 y posicionando a la empresa para el crecimiento futuro. Tras su salida, fue destinado a codirigir la fábrica de Leipzig.

## **La Era de la transformación digital y electrificación (2010-2024)**

### **Tomás Villén (2010-presente) - El transformador**

**Tomás Villén asumió el cargo de Director General de Porsche Ibérica el 1 de enero de 2010**, sustituyendo a Joachim Lamla. Con **15 años al frente de la compañía**, se ha convertido en el CEO con más longevidad en la historia de Porsche España.

**Perfil profesional:**

- 44 años al momento del nombramiento, licenciado en Derecho y MBA por la Universidad San Pablo (CEU)
- Amplia experiencia en el sector automovilístico: PSA, Smart, BMW, Seat Motor España
- **Experiencia directa en marcas premium** antes de llegar a Porsche

**Logros transformadores:**

**Crecimiento exponencial en ventas:**

- **Crecimiento del 78,6% en matriculaciones entre 2020-2024**: de 2.167 a 3.870 unidades
- En 2023, Porsche Ibérica facturó **439,36 millones de euros** (+24,82% vs 2022)
- Beneficio neto de **9,74 millones de euros en 2023**



{% raw %}

<canvas id="porscheChart" width="400" height="200"></canvas>

<script>
const config = {
    type: 'line',
    data: {
        labels: ['2020', '2021', '2022', '2023', '2024'],
        datasets: [{
            label: 'Matriculaciones Porsche España',
            data: [2167, 2423, 2782, 3275, 3870],
            borderColor: 'rgb(212, 175, 55)', // Color dorado de Porsche
            backgroundColor: 'rgba(212, 175, 55, 0.1)',
            borderWidth: 3,
            fill: true,
            tension: 0.2,
            pointBackgroundColor: 'rgb(212, 175, 55)',
            pointBorderColor: '#fff',
            pointBorderWidth: 2,
            pointRadius: 6
        }]
    },
    options: {
        responsive: true,
        plugins: {
            title: {
                display: true,
                text: 'Evolución de Matriculaciones de Porsche en España (2020-2024)',
                font: { size: 16, family: 'Arial, sans-serif' },
                color: '#333'
            }
        },
        scales: {
            y: {
                beginAtZero: false,
                min: 2000,
                title: { display: true, text: 'Número de Matriculaciones' },
                ticks: {
                    callback: function(value) {
                        return value.toLocaleString('es-ES');
                    }
                }
            },
            x: {
                title: { display: true, text: 'Año' }
            }
        }
    }
};

const ctx = document.getElementById('porscheChart').getContext('2d');
const porscheChart = new Chart(ctx, config);
</script>

{% endraw %}

Evolución de matriculaciones de Porsche en España durante el mandato de Tomás Villén (2020-2024)

**Liderazgo en electrificación:**

- **50% de las ventas actuales corresponden a modelos que se enchufan**
- **20% de las ventas corresponde al Taycan** (modelo 100% eléctrico)
- **95% de los Cayenne y Panamera vendidos se enchufan**
- Participación directa o indirecta en **el 50% de los cargadores de alta potencia instalados** en España y Portugal

**Excelencia en satisfacción del cliente:**

- **Puntuación de 9,7-9,8 sobre 10 en satisfacción del cliente**
- Los 24 Centros Porsche son **referencia en valoración de clientes**
- Red de concesionarios calificada como **"la más profesional y eficiente"**

Porsche ha conseguido una gran valoración en los [índices de satisfacción de cliente y ventas](https://mejorimposible.es/satisfaccion-porsche). 

**Innovación y sostenibilidad:**

- Lanzamiento exitoso del **Macan 100% eléctrico** con expectativas de 1.000 unidades en 2024
- Posicionamiento como **"expertos en movilidad eléctrica"**
- Implementación de iniciativas de **responsabilidad social corporativa** como el proyecto Suma


## **Impacto comparativo de cada CEO en las ventas**

### **Evolución de las Ventas por Periodo:**

**Era Heyl (1984-1997):**

- Inicio con 252 unidades en 1985
- Construcción de los fundamentos del mercado español
- Establecimiento de la red de distribución

**Era Schwarzenbauer (1997-2003):**

- Periodo de **"continua expansión"**
- Transformación estructural de la compañía
- Momento de **"dulzura empresarial"** al final de su mandato

**Era Lamla (2003-2010):**

- Gestión de **"varios retos con éxito"**
- Renovación profunda de productos
- Preparación para la era del Cayenne

**Era Villén (2010-presente):**

- **Crecimiento más sostenido y documentado** de la historia
- **78,6% de crecimiento en matriculaciones (2020-2024)**
- Transformación hacia la movilidad eléctrica
- Récords históricos en satisfacción del cliente


### **Factores de éxito de cada liderazgo:**

**Heyl** estableció las bases operativas y enfrentó los desafíos regulatorios iniciales con **determinación pionera**. **Schwarzenbauer** modernizó la estructura empresarial y preparó la expansión comercial con **visión estratégica**. **Lamla** consolidó el crecimiento y navegó las crisis con **estabilidad operativa**. **Villén** ha liderado la transformación digital y la electrificación con **innovación disruptiva**.

## **El legado actual y perspectivas futuras**

Bajo el liderazgo de Tomás Villén, Porsche Ibérica ha experimentado su **periodo de más éxito y transformador**. La empresa no solo ha logrado un crecimiento sustancial en ventas, sino que se ha posicionado como **líder en electrificación** y **referencia en satisfacción del cliente**.

La **estrategia de "lujo contemporáneo y deportivo"** implementada durante su mandato ha resultado en una empresa más resiliente, con una **estructura de ventas globalmente equilibrada** y preparada para los desafíos futuros del sector automovilístico.

Los 40 años de historia de Porsche en España demuestran cómo cada CEO ha contribuido de manera única al éxito de la marca, desde los cimientos establecidos por Heyl hasta la transformación digital liderada por Villén, creando una **narrativa de éxito sostenido y evolución constante** en el mercado ibérico.
