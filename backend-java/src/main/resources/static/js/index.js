var analyticsApp = new Vue({
    el: '#analyticsApp',
    data: {
        capabilities: {
            mode: 'local',
            mysqlEnabled: true,
            bigDataEnabled: false,
            profiles: []
        },
        filters: {
            month: '',
            city: ''
        },
        overview: {
            listingCount: 0,
            districtCount: 0,
            averageTotalPrice: 0,
            averageUnitPrice: 0
        },
        regions: [],
        trends: [],
        qualityRows: [],
        loading: false,
        compacting: false,
        errorMessage: '',
        statusMessage: '正在检测系统运行模式…',
        regionChart: null,
        trendChart: null
    },
    computed: {
        latestQuality: function () {
            return this.qualityRows.length ? this.qualityRows[0] : {qualityScore: 0};
        }
    },
    mounted: function () {
        this.regionChart = echarts.init(document.getElementById('regionChart'));
        this.trendChart = echarts.init(document.getElementById('trendChart'));
        window.addEventListener('resize', this.resizeCharts);
        this.loadCapabilities();
    },
    beforeDestroy: function () {
        window.removeEventListener('resize', this.resizeCharts);
    },
    methods: {
        loadCapabilities: function () {
            var vm = this;
            vm.$http.get('/api/system/capabilities').then(function (response) {
                vm.capabilities = response.body.data;
                vm.statusMessage = vm.capabilities.bigDataEnabled
                    ? 'bigdata 模式：使用 Hive 分析层。'
                    : 'local 模式：使用 MySQL 实时统计。';
                return vm.loadDashboard();
            }).catch(function (error) {
                vm.errorMessage = vm.responseMessage(error, '无法读取系统运行模式。');
            });
        },
        queryParams: function (includeMonth) {
            var params = {};
            if (includeMonth && this.filters.month) {
                params.month = this.filters.month;
            }
            if (this.filters.city) {
                params.city = this.filters.city;
            }
            return params;
        },
        loadDashboard: function () {
            var vm = this;
            vm.loading = true;
            vm.errorMessage = '';
            vm.statusMessage = vm.capabilities.bigDataEnabled
                ? '正在查询 Hive 分析层…'
                : '正在查询 MySQL 房源数据…';

            var baseUrl = vm.capabilities.bigDataEnabled
                ? '/api/analytics' : '/api/statistics';
            var requests = [
                vm.$http.get(baseUrl + '/overview', {
                    params: vm.queryParams(true)
                }),
                vm.$http.get(baseUrl + '/regions', {
                    params: Object.assign({limit: 10}, vm.queryParams(true))
                }),
                vm.$http.get(baseUrl + '/price-trends', {
                    params: Object.assign({months: 12}, vm.queryParams(false))
                })
            ];
            if (vm.capabilities.bigDataEnabled) {
                requests.push(vm.$http.get('/api/analytics/quality', {
                    params: {limit: 10}
                }));
            }

            Promise.all(requests).then(function (responses) {
                vm.overview = responses[0].body.data;
                vm.regions = responses[1].body.data || [];
                vm.trends = responses[2].body.data || [];
                vm.qualityRows = vm.capabilities.bigDataEnabled
                    ? (responses[3].body.data || []) : [];
                vm.renderRegionChart();
                vm.renderTrendChart();
                vm.statusMessage = vm.overview.listingCount
                    ? '分析数据已更新。'
                    : (vm.capabilities.bigDataEnabled
                        ? '分析层暂无数据，请先导入数据。'
                        : 'MySQL 暂无有效房源数据。');
            }).catch(function (error) {
                vm.errorMessage = vm.responseMessage(
                    error,
                    vm.capabilities.bigDataEnabled
                        ? '分析服务暂时不可用，请检查 HiveServer2 和分析表。'
                        : 'MySQL 统计服务暂时不可用。');
                vm.renderRegionChart();
                vm.renderTrendChart();
            }).finally(function () {
                vm.loading = false;
            });
        },
        compactData: function () {
            var vm = this;
            if (!vm.capabilities.bigDataEnabled) return;
            vm.compacting = true;
            vm.errorMessage = '';
            vm.statusMessage = '正在重写月份分区并合并 ORC 小文件…';
            vm.$http.post('/api/analytics/maintenance/compact').then(function (response) {
                var result = response.body.data;
                vm.statusMessage = '合并完成，耗时 ' + result.elapsedMillis + ' ms。正在刷新看板…';
                return vm.loadDashboard();
            }).catch(function (error) {
                vm.errorMessage = vm.responseMessage(error, '小文件合并失败。');
            }).finally(function () {
                vm.compacting = false;
            });
        },
        renderRegionChart: function () {
            var labels = this.regions.map(function (row) {
                return row.city + ' · ' + row.district;
            });
            var values = this.regions.map(function (row) {
                return row.averageUnitPrice;
            });
            this.regionChart.setOption({
                color: ['#0d8f83'],
                tooltip: {
                    trigger: 'axis',
                    valueFormatter: function (value) {
                        return Number(value).toLocaleString('zh-CN') + ' 元/㎡';
                    }
                },
                grid: {left: 18, right: 24, top: 24, bottom: 22, containLabel: true},
                xAxis: {
                    type: 'value',
                    axisLabel: {
                        formatter: function (value) {
                            return Math.round(value / 1000) + 'k';
                        }
                    },
                    splitLine: {lineStyle: {color: '#e8edf2'}}
                },
                yAxis: {
                    type: 'category',
                    inverse: true,
                    data: labels,
                    axisLabel: {width: 120, overflow: 'truncate'}
                },
                series: [{
                    name: '平均单价',
                    type: 'bar',
                    data: values,
                    barMaxWidth: 22,
                    itemStyle: {borderRadius: [0, 5, 5, 0]}
                }]
            }, true);
        },
        renderTrendChart: function () {
            var months = this.trends.map(function (row) { return row.month; });
            var prices = this.trends.map(function (row) { return row.averageUnitPrice; });
            this.trendChart.setOption({
                color: ['#e8a23a'],
                tooltip: {
                    trigger: 'axis',
                    valueFormatter: function (value) {
                        return Number(value).toLocaleString('zh-CN') + ' 元/㎡';
                    }
                },
                grid: {left: 18, right: 24, top: 24, bottom: 22, containLabel: true},
                xAxis: {
                    type: 'category',
                    boundaryGap: false,
                    data: months,
                    axisLabel: {rotate: months.length > 8 ? 35 : 0}
                },
                yAxis: {
                    type: 'value',
                    scale: true,
                    splitLine: {lineStyle: {color: '#e8edf2'}}
                },
                series: [{
                    name: '平均单价',
                    type: 'line',
                    smooth: true,
                    symbolSize: 7,
                    data: prices,
                    areaStyle: {color: 'rgba(232, 162, 58, .15)'}
                }]
            }, true);
        },
        resizeCharts: function () {
            if (this.regionChart) this.regionChart.resize();
            if (this.trendChart) this.trendChart.resize();
        },
        responseMessage: function (error, fallback) {
            return error && error.body && error.body.message
                ? error.body.message : fallback;
        },
        formatNumber: function (value) {
            return Number(value || 0).toLocaleString('zh-CN', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            });
        },
        formatInteger: function (value) {
            return Number(value || 0).toLocaleString('zh-CN', {
                maximumFractionDigits: 0
            });
        }
    }
});
