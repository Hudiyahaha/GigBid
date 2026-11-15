import { NextResponse } from 'next/server';
import { MongoClient } from 'mongodb';
import Stripe from 'stripe';
export interface Order { id: string; total: number }
