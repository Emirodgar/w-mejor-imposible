// Variables globales
let salesData = null;
let sentimentData = null;
let valuationData = null;
let marketEvolutionData = null;

// Configuración de colores para las marcas
const brandColors = {
    'Porsche': '#d5001c',
    'BMW': '#0066cc',
    'Audi': '#bb0a30',
    'Mercedes-Benz': '#a8a8a8'
};

// Configuración de Chart.js
Chart.defaults.color = '#b0b0b0';
Chart.defaults.backgroundColor = 'rgba(255, 107, 53, 0.1)';
Chart.defaults.borderColor = '#333';

// Inicialización del dashboard
document.addEventListener('DOMContentLoaded', function() {
    initializeDashboard();
    setupEventListeners();
    loadAllData();
});

// Configuración de event listeners
function setupEventListeners() {
    // Navegación
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('href').substring(1);
            showSection(targetId);
            updateActiveNavLink(this);
        });
    });

    // Filtros
    document.getElementById('year-filter').addEventListener('change', updateCharts);
    document.getElementById('brand-filter').addEventListener('change', function() {
        togglePorscheModels();
        updateCharts();
    });
    document.getElementById('model-filter').addEventListener('change', updateCharts);
}

// Mostrar/ocultar filtro de modelos de Porsche
function togglePorscheModels() {
    const brandFilter = document.getElementById('brand-filter');
    const porscheModels = document.getElementById('porsche-models');
    
    if (brandFilter.value === 'Porsche') {
        porscheModels.style.display = 'block';
    } else {
        porscheModels.style.display = 'none';
    }
}

// Navegación entre secciones
function showSection(sectionId) {
    // Ocultar todas las secciones
    document.querySelectorAll('.section').forEach(section => {
        section.classList.remove('active');
    });
    
    // Mostrar la sección seleccionada
    const targetSection = document.getElementById(sectionId);
    if (targetSection) {
        targetSection.classList.add('active');
    }
}

// Actualizar enlace activo en navegación
function updateActiveNavLink(activeLink) {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });
    activeLink.classList.add('active');
}

// Cargar todos los datos XML
async function loadAllData() {
    try {
        await Promise.all([
            loadSalesData(),
            loadSentimentData(),
            loadValuationData(),
            loadMarketEvolutionData()
        ]);
        
        updateHeaderStats();
        initializeCharts();
    } catch (error) {
        console.error('Error cargando datos:', error);
    }
}

// Cargar datos de ventas
async function loadSalesData() {
    try {
        const response = await fetch('data/sales_data.xml');
        const xmlText = await response.text();
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, 'text/xml');
        salesData = parseXMLToJSON(xmlDoc, 'sales');
    } catch (error) {
        console.error('Error cargando datos de ventas:', error);
    }
}

// Cargar datos de sentimiento
async function loadSentimentData() {
    try {
        const response = await fetch('data/sentiment_data.xml');
        const xmlText = await response.text();
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, 'text/xml');
        sentimentData = parseXMLToJSON(xmlDoc, 'sentiment');
    } catch (error) {
        console.error('Error cargando datos de sentimiento:', error);
    }
}

// Cargar datos de valoración
async function loadValuationData() {
    try {
        const response = await fetch('data/valuation_data.xml');
        const xmlText = await response.text();
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, 'text/xml');
        valuationData = parseXMLToJSON(xmlDoc, 'valuation');
    } catch (error) {
        console.error('Error cargando datos de valoración:', error);
    }
}

// Cargar datos de evolución del mercado
async function loadMarketEvolutionData() {
    try {
        const response = await fetch('data/market_evolution_data.xml');
        const xmlText = await response.text();
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, 'text/xml');
        marketEvolutionData = parseXMLToJSON(xmlDoc, 'market_evolution');
    } catch (error) {
        console.error('Error cargando datos de evolución del mercado:', error);
    }
}

// Parser XML a JSON
function parseXMLToJSON(xmlDoc, dataType) {
    const result = {};
    
    if (dataType === 'sales') {
        const brands = xmlDoc.querySelectorAll('brand');
        brands.forEach(brand => {
            const brandName = brand.getAttribute('name');
            result[brandName] = {};
            
            const models = brand.querySelectorAll('model');
            models.forEach(model => {
                const modelName = model.getAttribute('name');
                result[brandName][modelName] = {};
                
                const years = model.querySelectorAll('year');
                years.forEach(year => {
                    const yearValue = year.getAttribute('value');
                    result[brandName][modelName][yearValue] = {};
                    
                    const months = year.querySelectorAll('month');
                    months.forEach(month => {
                        const monthName = month.getAttribute('name');
                        const sales = parseInt(month.getAttribute('sales'));
                        result[brandName][modelName][yearValue][monthName] = sales;
                    });
                });
            });
        });
    } else if (dataType === 'sentiment') {
        const brands = xmlDoc.querySelectorAll('brand');
        brands.forEach(brand => {
            const brandName = brand.getAttribute('name');
            result[brandName] = {};
            
            const years = brand.querySelectorAll('year');
            years.forEach(year => {
                const yearValue = year.getAttribute('value');
                result[brandName][yearValue] = {};
                
                const months = year.querySelectorAll('month');
                months.forEach(month => {
                    const monthName = month.getAttribute('name');
                    const score = parseFloat(month.getAttribute('score'));
                    result[brandName][yearValue][monthName] = score;
                });
            });
        });
    } else if (dataType === 'valuation') {
        const brands = xmlDoc.querySelectorAll('brand');
        brands.forEach(brand => {
            const brandName = brand.getAttribute('name');
            result[brandName] = {};
            
            const models = brand.querySelectorAll('model');
            models.forEach(model => {
                const modelName = model.getAttribute('name');
                const rating = parseFloat(model.getAttribute('rating'));
                const reviews = parseInt(model.getAttribute('reviews'));
                result[brandName][modelName] = { rating, reviews };
            });
        });
    } else if (dataType === 'market_evolution') {
        const years = xmlDoc.querySelectorAll('year');
        years.forEach(year => {
            const yearValue = year.getAttribute('value');
            result[yearValue] = {};
            
            const months = year.querySelectorAll('month');
            months.forEach(month => {
                const monthName = month.getAttribute('name');
                const porscheSales = parseInt(month.getAttribute('porsche_sales'));
                const totalMarketSales = parseInt(month.getAttribute('total_market_sales'));
                result[yearValue][monthName] = { porscheSales, totalMarketSales };
            });
        });
    }
    
    return result;
}

// Actualizar estadísticas del header
function updateHeaderStats() {
    if (!salesData || !sentimentData) return;
    
    const year = document.getElementById('year-filter').value;
    
    // Calcular ventas totales
    let totalSales = 0;
    Object.keys(salesData).forEach(brand => {
        Object.keys(salesData[brand]).forEach(model => {
            if (salesData[brand][model][year]) {
                Object.values(salesData[brand][model][year]).forEach(sales => {
                    totalSales += sales;
                });
            }
        });
    });
    
    // Calcular sentimiento promedio
    let totalSentiment = 0;
    let sentimentCount = 0;
    Object.keys(sentimentData).forEach(brand => {
        if (sentimentData[brand][year]) {
            Object.values(sentimentData[brand][year]).forEach(score => {
                totalSentiment += score;
                sentimentCount++;
            });
        }
    });
    
    const avgSentiment = sentimentCount > 0 ? (totalSentiment / sentimentCount).toFixed(1) : 0;
    
    document.getElementById('total-sales').textContent = totalSales.toLocaleString();
    document.getElementById('avg-sentiment').textContent = avgSentiment;
}

// Inicializar todos los gráficos
function initializeCharts() {
    createPorscheSalesChart();
    createPorscheEvolutionChart();
    createBrandComparisonChart();
    createMarketShareChart();
    createMarketEvolutionChart();
    createSentimentChart();
    createSentimentEvolutionChart();
    createRatingChart();
    createReviewsChart();
}

// Actualizar todos los gráficos cuando cambian los filtros
function updateCharts() {
    updateHeaderStats();
    createPorscheSalesChart();
    createPorscheEvolutionChart();
    createBrandComparisonChart();
    createMarketShareChart();
    createMarketEvolutionChart();
    createSentimentChart();
    createSentimentEvolutionChart();
    createRatingChart();
    createReviewsChart();
}

// Gráfico de ventas de Porsche por modelo
function createPorscheSalesChart() {
    const ctx = document.getElementById('porsche-sales-chart');
    if (!ctx || !salesData) return;
    
    const year = document.getElementById('year-filter').value;
    const modelFilter = document.getElementById('model-filter').value;
    
    const porscheData = salesData['Porsche'];
    const labels = [];
    const data = [];
    const colors = ['#d5001c', '#ff6b35', '#ff8c42', '#ffa726'];
    
    let modelIndex = 0;
    Object.keys(porscheData).forEach(model => {
        if (modelFilter === 'all' || modelFilter === model) {
            if (porscheData[model][year]) {
                const totalSales = Object.values(porscheData[model][year]).reduce((sum, sales) => sum + sales, 0);
                labels.push(model);
                data.push(totalSales);
            }
        }
    });
    
    // Destruir gráfico existente si existe
    if (window.porscheSalesChart) {
        window.porscheSalesChart.destroy();
    }
    
    window.porscheSalesChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: colors.slice(0, labels.length),
                borderColor: '#1e1e1e',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#b0b0b0',
                        padding: 20
                    }
                }
            }
        }
    });
}

// Gráfico de evolución mensual de Porsche
function createPorscheEvolutionChart() {
    const ctx = document.getElementById('porsche-evolution-chart');
    if (!ctx || !salesData) return;
    
    const year = document.getElementById('year-filter').value;
    const modelFilter = document.getElementById('model-filter').value;
    
    const porscheData = salesData['Porsche'];
    const months = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                   'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
    
    const datasets = [];
    
    Object.keys(porscheData).forEach((model, index) => {
        if (modelFilter === 'all' || modelFilter === model) {
            if (porscheData[model][year]) {
                const data = months.map(month => porscheData[model][year][month] || 0);
                datasets.push({
                    label: model,
                    data: data,
                    borderColor: ['#d5001c', '#ff6b35', '#ff8c42', '#ffa726'][index],
                    backgroundColor: ['#d5001c', '#ff6b35', '#ff8c42', '#ffa726'][index] + '20',
                    tension: 0.4,
                    fill: false
                });
            }
        }
    });
    
    // Destruir gráfico existente si existe
    if (window.porscheEvolutionChart) {
        window.porscheEvolutionChart.destroy();
    }
    
    window.porscheEvolutionChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: months,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: '#333'
                    },
                    ticks: {
                        color: '#b0b0b0'
                    }
                },
                x: {
                    grid: {
                        color: '#333'
                    },
                    ticks: {
                        color: '#b0b0b0'
                    }
                }
            },
            plugins: {
                legend: {
                    labels: {
                        color: '#b0b0b0'
                    }
                }
            }
        }
    });
}

// Gráfico de comparación de marcas
function createBrandComparisonChart() {
    const ctx = document.getElementById('brand-comparison-chart');
    if (!ctx || !salesData) return;
    
    const year = document.getElementById('year-filter').value;
    const brandFilter = document.getElementById('brand-filter').value;
    
    const labels = [];
    const data = [];
    const colors = [];
    
    Object.keys(salesData).forEach(brand => {
        if (brandFilter === 'all' || brandFilter === brand) {
            let totalSales = 0;
            Object.keys(salesData[brand]).forEach(model => {
                if (salesData[brand][model][year]) {
                    Object.values(salesData[brand][model][year]).forEach(sales => {
                        totalSales += sales;
                    });
                }
            });
            
            labels.push(brand);
            data.push(totalSales);
            colors.push(brandColors[brand]);
        }
    });
    
    // Destruir gráfico existente si existe
    if (window.brandComparisonChart) {
        window.brandComparisonChart.destroy();
    }
    
    window.brandComparisonChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Ventas Totales',
                data: data,
                backgroundColor: colors,
                borderColor: colors,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: '#333'
                    },
                    ticks: {
                        color: '#b0b0b0'
                    }
                },
                x: {
                    grid: {
                        color: '#333'
                    },
                    ticks: {
                        color: '#b0b0b0'
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });
}

// Gráfico de cuota de mercado
function createMarketShareChart() {
    const ctx = document.getElementById('market-share-chart');
    if (!ctx || !salesData) return;
    
    const year = document.getElementById('year-filter').value;
    
    const labels = [];
    const data = [];
    const colors = [];
    
    Object.keys(salesData).forEach(brand => {
        let totalSales = 0;
        Object.keys(salesData[brand]).forEach(model => {
            if (salesData[brand][model][year]) {
                Object.values(salesData[brand][model][year]).forEach(sales => {
                    totalSales += sales;
                });
            }
        });
        
        labels.push(brand);
        data.push(totalSales);
        colors.push(brandColors[brand]);
    });
    
    // Destruir gráfico existente si existe
    if (window.marketShareChart) {
        window.marketShareChart.destroy();
    }
    
    window.marketShareChart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: colors,
                borderColor: '#1e1e1e',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#b0b0b0',
                        padding: 20
                    }
                }
            }
        }
    });
}

// Gráfico de evolución del mercado
function createMarketEvolutionChart() {
    const ctx = document.getElementById('market-evolution-chart');
    if (!ctx || !marketEvolutionData) return;
    
    const year = document.getElementById('year-filter').value;
    const months = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                   'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
    
    const porscheData = months.map(month => marketEvolutionData[year][month]?.porscheSales || 0);
    const marketData = months.map(month => marketEvolutionData[year][month]?.totalMarketSales || 0);
    
    // Destruir gráfico existente si existe
    if (window.marketEvolutionChart) {
        window.marketEvolutionChart.destroy();
    }
    
    window.marketEvolutionChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: months,
            datasets: [{
                label: 'Ventas Porsche',
                data: porscheData,
                borderColor: '#d5001c',
                backgroundColor: '#d5001c20',
                tension: 0.4,
                yAxisID: 'y'
            }, {
                label: 'Mercado Total',
                data: marketData,
                borderColor: '#ff6b35',
                backgroundColor: '#ff6b3520',
                tension: 0.4,
                yAxisID: 'y1'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            scales: {
                x: {
                    display: true,
                    grid: {
                        color: '#333'
                    },
                    ticks: {
                        color: '#b0b0b0'
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    grid: {
                        color: '#333'
                    },
                    ticks: {
                        color: '#b0b0b0'
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: {
                        drawOnChartArea: false,
                    },
                    ticks: {
                        color: '#b0b0b0'
                    }
                }
            },
            plugins: {
                legend: {
                    labels: {
                        color: '#b0b0b0'
                    }
                }
            }
        }
    });
}

// Gráfico de sentimiento por marca
function createSentimentChart() {
    const ctx = document.getElementById('sentiment-chart');
    if (!ctx || !sentimentData) return;
    
    const year = document.getElementById('year-filter').value;
    const brandFilter = document.getElementById('brand-filter').value;
    
    const labels = [];
    const data = [];
    const colors = [];
    
    Object.keys(sentimentData).forEach(brand => {
        if (brandFilter === 'all' || brandFilter === brand) {
            if (sentimentData[brand][year]) {
                const avgSentiment = Object.values(sentimentData[brand][year]).reduce((sum, score) => sum + score, 0) / 12;
                labels.push(brand);
                data.push(avgSentiment.toFixed(1));
                colors.push(brandColors[brand]);
            }
        }
    });
    
    // Destruir gráfico existente si existe
    if (window.sentimentChart) {
        window.sentimentChart.destroy();
    }
    
    window.sentimentChart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Sentimiento Promedio',
                data: data,
                borderColor: '#ff6b35',
                backgroundColor: '#ff6b3530',
                pointBackgroundColor: colors,
                pointBorderColor: colors,
                pointRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                r: {
                    beginAtZero: true,
                    max: 10,
                    grid: {
                        color: '#333'
                    },
                    pointLabels: {
                        color: '#b0b0b0'
                    },
                    ticks: {
                        color: '#b0b0b0'
                    }
                }
            },
            plugins: {
                legend: {
                    labels: {
                        color: '#b0b0b0'
                    }
                }
            }
        }
    });
}

// Gráfico de evolución del sentimiento
function createSentimentEvolutionChart() {
    const ctx = document.getElementById('sentiment-evolution-chart');
    if (!ctx || !sentimentData) return;
    
    const year = document.getElementById('year-filter').value;
    const brandFilter = document.getElementById('brand-filter').value;
    const months = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                   'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
    
    const datasets = [];
    
    Object.keys(sentimentData).forEach((brand, index) => {
        if (brandFilter === 'all' || brandFilter === brand) {
            if (sentimentData[brand][year]) {
                const data = months.map(month => sentimentData[brand][year][month] || 0);
                datasets.push({
                    label: brand,
                    data: data,
                    borderColor: brandColors[brand],
                    backgroundColor: brandColors[brand] + '20',
                    tension: 0.4,
                    fill: false
                });
            }
        }
    });
    
    // Destruir gráfico existente si existe
    if (window.sentimentEvolutionChart) {
        window.sentimentEvolutionChart.destroy();
    }
    
    window.sentimentEvolutionChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: months,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 10,
                    grid: {
                        color: '#333'
                    },
                    ticks: {
                        color: '#b0b0b0'
                    }
                },
                x: {
                    grid: {
                        color: '#333'
                    },
                    ticks: {
                        color: '#b0b0b0'
                    }
                }
            },
            plugins: {
                legend: {
                    labels: {
                        color: '#b0b0b0'
                    }
                }
            }
        }
    });
}

// Gráfico de rating por modelo
function createRatingChart() {
    const ctx = document.getElementById('rating-chart');
    if (!ctx || !valuationData) return;
    
    const brandFilter = document.getElementById('brand-filter').value;
    
    const labels = [];
    const data = [];
    const colors = [];
    
    Object.keys(valuationData).forEach(brand => {
        if (brandFilter === 'all' || brandFilter === brand) {
            Object.keys(valuationData[brand]).forEach(model => {
                labels.push(`${brand} ${model}`);
                data.push(valuationData[brand][model].rating);
                colors.push(brandColors[brand]);
            });
        }
    });
    
    // Destruir gráfico existente si existe
    if (window.ratingChart) {
        window.ratingChart.destroy();
    }
    
    window.ratingChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Rating',
                data: data,
                backgroundColor: colors,
                borderColor: colors,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            scales: {
                y: {
                    grid: {
                        color: '#333'
                    },
                    ticks: {
                        color: '#b0b0b0'
                    }
                },
                x: {
                    beginAtZero: true,
                    max: 5,
                    grid: {
                        color: '#333'
                    },
                    ticks: {
                        color: '#b0b0b0'
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });
}

// Gráfico de número de reviews
function createReviewsChart() {
    const ctx = document.getElementById('reviews-chart');
    if (!ctx || !valuationData) return;
    
    const brandFilter = document.getElementById('brand-filter').value;
    
    const labels = [];
    const data = [];
    const colors = [];
    
    Object.keys(valuationData).forEach(brand => {
        if (brandFilter === 'all' || brandFilter === brand) {
            Object.keys(valuationData[brand]).forEach(model => {
                labels.push(`${brand} ${model}`);
                data.push(valuationData[brand][model].reviews);
                colors.push(brandColors[brand]);
            });
        }
    });
    
    // Destruir gráfico existente si existe
    if (window.reviewsChart) {
        window.reviewsChart.destroy();
    }
    
    window.reviewsChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: colors,
                borderColor: '#1e1e1e',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#b0b0b0',
                        padding: 20
                    }
                }
            }
        }
    });
}

// Función de inicialización del dashboard
function initializeDashboard() {
    console.log('Dashboard inicializado correctamente');
}

