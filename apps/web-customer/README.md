# SahulatKar - Shariah-Compliant Financial Platform

A premium, modern frontend for a Shariah-compliant financial platform built with Next.js, Tailwind CSS, and Framer Motion. This application provides ethical financing solutions with a focus on user experience and visual excellence.

## 🌟 Features

### Core Functionality
- **User Registration & KYC**: Complete onboarding with CNIC capture and verification
- **Paste-and-Go Shopping**: Instant product URL extraction from major e-commerce platforms
- **Universal Cart**: Aggregate products from multiple stores with unified financing
- **Shariah-Compliant Financing**: Murabaha model with transparent profit rates
- **Account Management**: Secure login, verification, and dashboard

### Design & UX
- **Premium Visual Design**: Modern, clean interface with orange/gray color scheme
- **Advanced Animations**: Smooth transitions, micro-interactions, and 3D effects
- **Responsive Layout**: Fully optimized for all devices
- **Glassmorphism Effects**: Modern UI elements with backdrop blur
- **Floating Elements**: Dynamic animations for enhanced user engagement

### Technical Stack
- **Frontend**: Next.js 16 with TypeScript
- **Styling**: Tailwind CSS with custom design system
- **Animations**: Framer Motion for advanced motion design
- **Icons**: Lucide React for consistent iconography
- **UI Components**: Custom component library with Radix UI primitives

## 🚀 Getting Started

### Prerequisites
- Node.js 18+ 
- npm, yarn, pnpm, or bun

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd saulatkar-frontend
```

2. Install dependencies:
```bash
npm install
# or
yarn install
# or
pnpm install
```

3. Run the development server:
```bash
npm run dev
# or
yarn dev
# or
pnpm dev
```

4. Open [http://localhost:3000](http://localhost:3000) in your browser.

## 📁 Project Structure

```
src/
├── app/                    # Next.js app router pages
│   ├── auth/              # Authentication pages
│   ├── cart/              # Shopping cart
│   ├── financing/         # Financing module
│   ├── kyc/               # KYC processes
│   └── shop/              # Shopping interfaces
├── components/
│   ├── ui/                # Reusable UI components
│   └── layout/            # Layout components
└── lib/                   # Utility functions
```

## 🎨 Design System

### Color Palette
- **Primary**: Orange gradient (500-600)
- **Secondary**: Gray scale (50-900)
- **Accent**: Green for success states
- **Background**: Light orange/gray gradients

### Typography
- **Font Family**: Inter (system-ui fallback)
- **Headings**: Bold, responsive sizing
- **Body**: Clean, readable text

### Animations
- **Page Transitions**: Smooth fade and slide effects
- **Micro-interactions**: Hover states and button animations
- **3D Effects**: Floating elements and depth perception
- **Loading States**: Elegant skeleton screens

## 🔧 Key Features Implementation

### Authentication Flow
1. **Registration**: Split-screen design with trust indicators
2. **Verification**: OTP-based mobile verification
3. **KYC Process**: CNIC capture with data extraction

### Shopping Experience
1. **Paste-and-Go**: URL extraction from 8+ major platforms
2. **Product Display**: Native cards with variant selection
3. **Universal Cart**: Multi-store aggregation

### Financing Module
1. **Plan Selection**: 6, 12, 18 month options
2. **KFS Display**: Transparent cost breakdown
3. **Wakalah Agreement**: Digital contract signing

## 🎯 Performance Optimizations

- **Image Optimization**: Next.js Image component
- **Code Splitting**: Automatic route-based splitting
- **Lazy Loading**: Component-level lazy loading
- **Animation Performance**: GPU-accelerated transforms

## 📱 Responsive Design

- **Mobile First**: Progressive enhancement approach
- **Touch Interactions**: Optimized for mobile devices
- **Flexible Grids**: Adaptive layouts for all screen sizes
- **Performance**: Optimized for mobile networks

## 🔒 Security Features

- **Input Validation**: Client and server-side validation
- **XSS Protection**: Built-in Next.js security
- **CSRF Protection**: Token-based protection
- **Secure Headers**: Optimized security headers

## 🌐 Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## 📄 License

This project is proprietary and confidential.

## 🤝 Contributing

Please follow the established coding standards and design patterns when contributing to this project.

---

Built with ❤️ using Next.js, Tailwind CSS, and Framer Motion
