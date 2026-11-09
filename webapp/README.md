# Project 3: In-Browser Real Estate Discount Estimator

A minimalist, mobile-first, responsive web application that performs 100% client-side machine learning inference to calculate fair market property valuations and evaluate listing discounts across Greater Vancouver and Fraser Valley.

## Highlights

- **Zero Manual Spec Entry**: Instant address lookup and automatic resolution of bedrooms, bathrooms, square footage, property type, location coordinates, amenities, and asking price.
- **In-Browser ML Engine**: Replicates pandas and scikit-learn feature engineering, interaction expansion, robust scaling, and Ridge regression inference entirely in client-side TypeScript.
- **Real-Time Discount Analysis**: Instantly calculates dollar discount (`Fair Market Value - Listed Price`) and percentage discount, displaying high-visibility visual badges:
  - **Underpriced / Discount**: Green badge with savings amount and percent below market.
  - **Above Model / Premium**: Red badge with premium amount and percent above market.
  - **Fairly Priced**: Neutral badge indicating alignment with model target.
- **Minimalist Empty-Canvas Aesthetic**: Plain, spacious, centered focus with zero clutter.
- **Interactive Tuning**: Optional collapsible drawer to adjust specs in real-time.

## Technology Stack

- **Framework**: Vite + React 18 + TypeScript
- **Styling**: TailwindCSS
- **Icons**: Lucide React
- **ML Runtime**: In-browser linear/ridge dot product engine with `RobustScaler` (`browserModel.ts`)

## Development & Build

```bash
cd /workspace/webapp

# Development server
npm run dev

# Production build
npm run build
```
The compiled output is located in `dist/`.
