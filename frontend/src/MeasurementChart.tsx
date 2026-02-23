import { useEffect, useMemo, useRef, useState } from 'react'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  type ChartOptions,
} from 'chart.js'
import type { Measurement } from './types'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

const MOBILE_BREAKPOINT = 768

type MeasurementChartProps = {
  data: Measurement[]
  dark: boolean
}

function getInitialIsMobile(): boolean {
  if (typeof window === 'undefined') return false
  return window.innerWidth <= MOBILE_BREAKPOINT
}

function getChartOptions(isMobile: boolean, dark: boolean): ChartOptions<'line'> {
  const darkGridColor = 'rgba(148, 163, 184, 0.34)'
  const lightGridColor = 'rgba(85, 96, 112, 0.18)'
  const gridColor = dark ? darkGridColor : lightGridColor

  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'index', intersect: false },
    elements: {
      point: {
        radius: 0,
        hoverRadius: 0,
      },
    },
    plugins: {
      tooltip: {
        enabled: false,
      },
      legend: {
        position: 'top',
      },
    },
    scales: {
      x: {
        grid: {
          display: true,
          drawOnChartArea: true,
          drawTicks: true,
          color: gridColor,
        },
        ticks: {
          maxTicksLimit: isMobile ? 12 : 24,
        },
      },
      y1: {
        type: 'linear',
        display: true,
        position: 'left',
        title: { display: true, text: 'CO2 ppm' },
        grid: {
          color: gridColor,
        },
      },
      y2: {
        type: 'linear',
        display: true,
        position: 'right',
        title: { display: !isMobile, text: 'Temperature / Humidity' },
        ticks: { display: !isMobile },
        grid: { drawOnChartArea: false, color: gridColor },
      },
    },
  }
}

export default function MeasurementChart({ data, dark }: MeasurementChartProps) {
  const [isMobile, setIsMobile] = useState<boolean>(getInitialIsMobile)
  const chartRef = useRef<any>(null)

  useEffect(() => {
    const handler = () => {
      setIsMobile(window.innerWidth <= MOBILE_BREAKPOINT)
      requestAnimationFrame(() => {
        try {
          chartRef.current?.chartInstance?.resize?.()
          chartRef.current?.resize?.()
          chartRef.current?.update?.()
        } catch {}
      })
    }

    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])

  const chartData = useMemo(() => {
    const labels = data.map((item) =>
      new Date(item.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    )
    const co2 = data.map((item) => item.co2)
    const temp = data.map((item) => item.temperature)
    const hum = data.map((item) => item.humidity)

    return {
      labels,
      datasets: [
        {
          label: 'CO2 (ppm)',
          data: co2,
          borderColor: 'rgb(200,20,20)',
          yAxisID: 'y1',
          fill: false,
        },
        {
          label: 'Temperature (\u00B0C)',
          data: temp,
          borderColor: 'rgb(20,100,200)',
          yAxisID: 'y2',
          fill: false,
        },
        {
          label: 'Humidity (%)',
          data: hum,
          borderColor: 'rgb(20,200,100)',
          yAxisID: 'y2',
          fill: false,
        },
      ],
    }
  }, [data])

  const chartOptions = useMemo(() => getChartOptions(isMobile, dark), [isMobile, dark])

  return <Line ref={chartRef} data={chartData} options={chartOptions} />
}
